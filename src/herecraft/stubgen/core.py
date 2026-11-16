"""herecraft.stubgen.core — Generate Python .pyi stubs from Java classes via ReflectWrapper."""

from __future__ import annotations

import ast
from collections import deque
from collections.abc import Iterable
import keyword
from logging import getLogger
from pathlib import Path
import shutil
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from herecraft._internals.javans import ReflectWrapper

logger = getLogger("herecraft.stubgen.core")

BASIC_TYPE_MAPPING: Final[dict[str, str]] = {
    "void": "None",
    "byte": "int",
    "short": "int",
    "int": "int",
    "long": "int",
    "float": "float",
    "double": "float",
    "char": "str",
    "boolean": "bool",
    "java.lang.String": "str",
    "java.lang.Object": "object",
    "java.lang.Boolean": "bool",
    "java.lang.Integer": "int",
    "java.lang.Long": "int",
    "java.lang.Float": "float",
    "java.lang.Double": "float",
    "java.lang.Character": "str",
    "java.lang.Byte": "int",
    "java.lang.Short": "int",
    "java.lang.Void": "None",
}

# Java FQN → (module, name) for Python stdlib equivalents
# Based on JEP's extended PyJObject behaviour (wiki: Accessing-Java-Objects-in-Python):
# - java.lang.Iterable → __iter__ (Iterable)
# - java.lang.Iterator → __next__ (Iterator)
# - java.util.Collection → __len__ + __contains__ (Collection)
# - java.util.List → __getitem__ + __setitem__ (MutableSequence)
# - java.util.Map → __getitem__ + __setitem__ + keys/items (MutableMapping)
# - java.lang.AutoCloseable / java.io.Closeable → __enter__ + __exit__ (AbstractContextManager)
# - java.lang.Comparable → supports comparison (no direct Python ABC, use protocol)
STDLIB_TYPE_MAPPING: Final[dict[str, tuple[str, str]]] = {
    "java.lang.Iterable": ("herecraft._internals.typedefs", "JIterable"),
    "java.lang.Comparable": ("herecraft._internals.typedefs", "JComparable"),
    "java.lang.Runnable": ("herecraft._internals.typedefs", "JRunnable"),
    "java.lang.AutoCloseable": ("herecraft._internals.typedefs", "JAutoCloseable"),
    "java.io.Closeable": ("herecraft._internals.typedefs", "JAutoCloseable"),
    "java.util.Iterator": ("herecraft._internals.typedefs", "JIterator"),
    "java.util.Collection": ("herecraft._internals.typedefs", "JCollection"),
    "java.util.List": ("herecraft._internals.typedefs", "JList"),
    "java.util.Set": ("herecraft._internals.typedefs", "JSet"),
    "java.util.SortedSet": ("herecraft._internals.typedefs", "JSet"),
    "java.util.Map": ("herecraft._internals.typedefs", "JMap"),
    "java.util.SortedMap": ("herecraft._internals.typedefs", "JMap"),
    "java.util.Queue": ("herecraft._internals.typedefs", "JCollection"),
    "java.util.Deque": ("herecraft._internals.typedefs", "JCollection"),
    "java.util.Comparator": ("collections.abc", "Callable"),
    "java.util.function.Consumer": ("collections.abc", "Callable"),
    "java.util.function.Supplier": ("collections.abc", "Callable"),
    "java.util.function.Function": ("collections.abc", "Callable"),
    "java.util.function.Predicate": ("collections.abc", "Callable"),
}

# Dunder method stubs to inject when generating a specific Java interface class.
# Key: canonical Java class name that IS the interface being generated.
# Value: list of (method_source_str) snippets to append to the class body.
# JEP adds these at runtime; we inject them into the interface stub so subclasses
# inherit them without having to redeclare. Arrays are handled separately.
_CLOSEABLE_PATCH = [
    "def __enter__(self) -> Self: ...",
    "def __exit__(self, tp: type[BaseException] | None, val: BaseException | None, tb: object) -> None: ...",
]

INTERFACE_PATCH: Final[dict[str, list[str]]] = {
    "java.lang.Iterable": [
        "def __iter__(self) -> Iterator[T]: ...",
    ],
    "java.util.Iterator": [
        "def __next__(self) -> T: ...",
        "def __iter__(self) -> Iterator[T]: return self",
    ],
    "java.util.Collection": [
        "def __len__(self) -> int: ...",
        "def __contains__(self, item: object) -> bool: ...",
    ],
    "java.util.List": [
        "def __getitem__(self, index: int) -> E: ...",
        "def __setitem__(self, index: int, value: E) -> None: ...",
    ],
    "java.util.Map": [
        "def __getitem__(self, key: K) -> V: ...",
        "def __setitem__(self, key: K, value: V) -> None: ...",
    ],
    "java.lang.AutoCloseable": _CLOSEABLE_PATCH,
    "java.io.Closeable": _CLOSEABLE_PATCH,
    "java.lang.Object": [
        "def __str__(self) -> str: ...",
        "def __hash__(self) -> int: ...",
        "def __eq__(self, other: object) -> bool: ...",
    ],
}

# typing names that may be used in a stub
_TYPING_NAMES = frozenset({"Any", "ClassVar", "Final", "final", "overload"})
# abc names
_ABC_NAMES = frozenset({"abstractmethod"})


class _ImportTracker:
    """Tracks which names from each module are actually used while building a stub."""

    def __init__(self) -> None:
        self.typing: set[str] = set()
        self.abc: set[str] = set()
        self.stdlib: dict[str, set[str]] = {}  # module → {name}
        self.java: dict[str, set[str]] = {}  # java_package → {ClassName}

    def need_typing(self, name: str) -> None:
        self.typing.add(name)

    def need_abc(self, name: str) -> None:
        self.abc.add(name)

    def need_stdlib(self, module: str, name: str) -> None:
        self.stdlib.setdefault(module, set()).add(name)

    def need_java(self, fqn: str) -> None:
        parts = fqn.rsplit(".", 1)
        if len(parts) == 2:
            self.java.setdefault(parts[0], set()).add(parts[1])

    def build_imports(self) -> list[ast.stmt]:
        stmts: list[ast.stmt] = []
        if self.typing:
            stmts.append(
                ast.ImportFrom(
                    module="typing",
                    names=[ast.alias(n) for n in sorted(self.typing)],
                    level=0,
                )
            )
        if self.abc:
            stmts.append(
                ast.ImportFrom(
                    module="abc",
                    names=[ast.alias(n) for n in sorted(self.abc)],
                    level=0,
                )
            )
        for mod in sorted(self.stdlib):
            stmts.append(
                ast.ImportFrom(
                    module=mod,
                    names=[ast.alias(n) for n in sorted(self.stdlib[mod])],
                    level=0,
                )
            )
        for pkg in sorted(self.java):
            stmts.append(
                ast.ImportFrom(
                    module=pkg,
                    names=[ast.alias(n) for n in sorted(self.java[pkg])],
                    level=0,
                )
            )
        return stmts


class StubGenerator:
    """Generates Python .pyi stub files from Java classes via ReflectWrapper."""

    output_dir: Path

    def __init__(self, output_dir: str) -> None:
        self.output_dir = Path(output_dir)
        from herecraft._internals.javans import ReflectWrapper

        self._wrapper: type[ReflectWrapper] = ReflectWrapper
        # Use context classloader by default so mod-loaded classes are resolvable
        from java.lang import Thread

        self._classloader: Any = Thread.currentThread().getContextClassLoader()

    def _load_class(self, java_class_name: str) -> Any:
        """Load a Java class using the stored classloader."""
        return self._classloader.loadClass(java_class_name)

    def generate(self, java_class_name: str) -> Path:
        """Generate a .pyi stub for a single Java class. Appends to the package file."""
        if not _is_stubgable(java_class_name):
            raise ValueError(f"Skipping non-stubgable class: {java_class_name}")
        jclass = self._load_class(java_class_name)
        rcls = self._wrapper.forClass(jclass)
        return self._write_class(rcls, java_class_name)

    def consolidate(self) -> None:
        """Merge any flat pkg.pyi into pkg/__init__.pyi where both exist.
        Also rewrites merged files to have a single unified import header.
        """
        seen_dirs: set[Path] = set()
        for pyi in sorted(self.output_dir.rglob("*.pyi")):
            sibling_dir = pyi.with_suffix("")
            if sibling_dir.is_dir():
                init = sibling_dir / "__init__.pyi"
                content = pyi.read_text(encoding="utf-8")
                if init.exists():
                    with open(init, "a", encoding="utf-8") as f:
                        _ = f.write("\n\n")
                        _ = f.write(content)
                    seen_dirs.add(init)
                else:
                    _ = shutil.move(str(pyi), str(init))
                    seen_dirs.add(init)
                    continue
                pyi.unlink()
                logger.info("Consolidated %s -> %s", pyi, init)

        for pyi in self.output_dir.rglob("*.pyi"):
            _unify_imports(pyi)

    def _write_classes_to_file(self, path: Path, tracker: _ImportTracker, class_defs: list[ast.ClassDef]) -> None:
        """Write (or append) class definitions to a stub file.

        On first write: full header + classes.
        On append: classes only — the file header is rewritten via rewrite_imports().
        """
        if not path.exists():
            body: list[ast.stmt] = [*tracker.build_imports(), *class_defs]
            source = ast.unparse(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])))
            _ = path.write_text(source + "\n\n", encoding="utf-8")
        else:
            # Append only class defs, then rewrite the import header
            class_source = "\n\n".join(ast.unparse(ast.fix_missing_locations(cd)) for cd in class_defs)
            with open(path, "a", encoding="utf-8") as f:
                _ = f.write("\n\n")
                _ = f.write(class_source)
                _ = f.write("\n\n")
            self._rewrite_imports(path, tracker)

    def _rewrite_imports(self, path: Path, new_tracker: _ImportTracker) -> None:
        """Merge new imports into the existing file's import header."""
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)

        # Collect existing import lines at the top (before first class/blank body)
        import_end = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("from ") or stripped.startswith("import ") or stripped == "":
                import_end = i + 1
            else:
                break

        existing_imports = "".join(lines[:import_end])
        rest = "".join(lines[import_end:])

        # Parse existing imports and merge with new tracker
        merged = _merge_import_source(existing_imports, new_tracker)
        _ = path.write_text(merged + rest, encoding="utf-8")

    def generate_batch(self, class_names: Iterable[str]) -> dict[str, Path | Exception]:
        """Generate stubs for multiple classes with per-file dependency sorting."""
        # Reflect all classes first
        reflected: dict[str, Any] = {}
        results: dict[str, Path | Exception] = {}
        for name in class_names:
            if not _is_stubgable(name):
                continue
            try:
                reflected[name] = self._wrapper.forClass(self._load_class(name))
            except Exception as e:
                logger.warning("Failed to reflect %s: %s", name, e)
                results[name] = e

        # Group by output file
        by_file: dict[Path, list[tuple[str, Any]]] = {}
        for name, rcls in reflected.items():
            path = self._determine_output_path(name)
            by_file.setdefault(path, []).append((name, rcls))

        # For each file: sort by intra-file dependency, then write
        for path, entries in by_file.items():
            ordered = _topo_sort(entries)
            path.parent.mkdir(parents=True, exist_ok=True)
            tracker = _ImportTracker()
            own_package = ordered[0][1].getPackageName() if ordered else ""
            class_defs: list[ast.ClassDef] = []
            for name, rcls in ordered:
                class_defs.append(self._build_class(rcls, tracker, own_package))
            self._write_classes_to_file(path, tracker, class_defs)
            for name, _ in ordered:
                results[name] = path
                logger.info("Generated stub: %s -> %s", name, path)

        return results

    def _write_class(self, rcls: Any, java_class_name: str) -> Path:
        tracker = _ImportTracker()
        own_package = rcls.getPackageName()
        class_def = self._build_class(rcls, tracker, own_package)
        output_path = self._determine_output_path(java_class_name)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_classes_to_file(output_path, tracker, [class_def])
        logger.info("Generated stub: %s -> %s", java_class_name, output_path)
        return output_path

    def _build_class(self, rcls: Any, tracker: _ImportTracker, own_package: str) -> ast.ClassDef:
        class_name = rcls.getSimpleName().replace("$", "_")

        bases: list[ast.expr] = []
        sup = rcls.getGenericSuperclass()
        if sup is not None and sup.getCanonicalName() != "java.lang.Object":
            bases.append(self._build_type_annotation(sup, tracker, own_package))
        for iface in rcls.getGenericInterfaces():
            bases.append(self._build_type_annotation(iface, tracker, own_package))

        type_params = self._build_type_params(rcls.getTypeParameters(), tracker, own_package)

        body: list[ast.stmt] = []

        for inner in rcls.getInnerClasses():
            body.append(self._build_class(inner, tracker, own_package))

        for field in rcls.getFields():
            body.append(self._build_field(field, tracker, own_package))

        methods_by_name: dict[str, list[Any]] = {}
        for method in rcls.getMethods():
            methods_by_name.setdefault(method.getName(), []).append(method)
        for methods in methods_by_name.values():
            body.extend(self._build_method(methods, tracker, own_package))

        constructors = list(rcls.getConstructors())
        if constructors:
            body.extend(self._build_constructor(constructors, tracker, own_package))

        # Inject JEP-provided dunder methods for patched interfaces
        canonical = rcls.getCanonicalName()
        if canonical in INTERFACE_PATCH:
            body.extend(_parse_patch_stubs(INTERFACE_PATCH[canonical], tracker))

        if not body:
            body.append(ast.Expr(ast.Constant(...)))

        return ast.ClassDef(
            name=class_name,
            bases=bases,
            keywords=[],
            body=body,
            decorator_list=[],
            type_params=type_params,
        )

    def _build_field(self, field: Any, tracker: _ImportTracker, own_package: str) -> ast.AnnAssign:
        name = field.getName()
        if name in keyword.kwlist:
            name = "___use_getattr_or_setattr_to_access_" + name

        annotation = self._build_type_annotation(field.getGenericType(), tracker, own_package)

        if field.isFinal():
            tracker.need_typing("Final")
            annotation = ast.Subscript(ast.Name("Final"), annotation)
        elif field.isStatic():
            tracker.need_typing("ClassVar")
            annotation = ast.Subscript(ast.Name("ClassVar"), annotation)

        return ast.AnnAssign(
            target=ast.Name(name),
            annotation=annotation,
            value=ast.Constant(...),
            simple=1,
        )

    def _build_method(self, methods: list[Any], tracker: _ImportTracker, own_package: str) -> list[ast.FunctionDef]:
        result: list[ast.FunctionDef] = []
        has_overload = len(methods) > 1

        for m in methods:
            decorators: list[ast.expr] = []
            if m.isAbstract():
                tracker.need_abc("abstractmethod")
                decorators.append(ast.Name("abstractmethod"))
            if has_overload:
                tracker.need_typing("overload")
                decorators.append(ast.Name("overload"))
            if m.isStatic():
                decorators.append(ast.Name("staticmethod"))
            if m.isFinal() and not has_overload:
                tracker.need_typing("final")
                decorators.append(ast.Name("final"))

            posonlyargs: list[ast.arg] = []
            vararg: ast.arg | None = None
            if not m.isStatic():
                posonlyargs.append(ast.arg("self"))

            for i, p in enumerate(m.getParameters()):
                param_name = p.getName() if p.isNamePresent() else f"arg{i}"
                if param_name in keyword.kwlist:
                    param_name = param_name + "_"
                ann = self._build_type_annotation(p.getType(), tracker, own_package)
                if p.isVarArg():
                    vararg = ast.arg(param_name, ann)
                else:
                    posonlyargs.append(ast.arg(param_name, ann))

            returns = self._build_type_annotation(m.getReturnType(), tracker, own_package)
            type_params = self._build_type_params(m.getTypeParameters(), tracker, own_package)

            name = m.getName()
            if name in keyword.kwlist:
                name = "___use_getattr_to_access_" + name

            result.append(
                ast.FunctionDef(
                    name=name,
                    args=ast.arguments(
                        posonlyargs=posonlyargs,
                        args=[],
                        vararg=vararg,
                        kwonlyargs=[],
                        kw_defaults=[],
                        defaults=[],
                    ),
                    body=[ast.Expr(ast.Constant(...))],
                    decorator_list=decorators,
                    returns=returns,
                    type_params=type_params,
                )
            )

        return result

    def _build_constructor(
        self, constructors: list[Any], tracker: _ImportTracker, own_package: str
    ) -> list[ast.FunctionDef]:
        result: list[ast.FunctionDef] = []
        has_overload = len(constructors) > 1

        for ctor in constructors:
            decorators: list[ast.expr] = []
            if has_overload:
                tracker.need_typing("overload")
                decorators.append(ast.Name("overload"))

            args: list[ast.arg] = [ast.arg("self")]
            vararg: ast.arg | None = None

            for i, p in enumerate(ctor.getParameters()):
                param_name = p.getName() if p.isNamePresent() else f"arg{i}"
                if param_name in keyword.kwlist:
                    param_name = param_name + "_"
                ann = self._build_type_annotation(p.getType(), tracker, own_package)
                if p.isVarArg():
                    vararg = ast.arg(param_name, ann)
                else:
                    args.append(ast.arg(param_name, ann))

            result.append(
                ast.FunctionDef(
                    name="__init__",
                    args=ast.arguments(
                        posonlyargs=args,
                        args=[],
                        vararg=vararg,
                        kwonlyargs=[],
                        kw_defaults=[],
                        defaults=[],
                    ),
                    body=[ast.Expr(ast.Constant(...))],
                    decorator_list=decorators,
                    returns=ast.Name("None"),
                    type_params=[],
                )
            )

        return result

    def _build_type_annotation(self, rtype: Any, tracker: _ImportTracker, own_package: str) -> ast.expr:
        if rtype is None:
            tracker.need_typing("Any")
            return ast.Name("Any")

        canonical = rtype.getCanonicalName()

        if canonical in BASIC_TYPE_MAPPING:
            return ast.Name(BASIC_TYPE_MAPPING[canonical])

        # Stdlib mapping (e.g. java.lang.Iterable → collections.abc.Iterable)
        if canonical in STDLIB_TYPE_MAPPING:
            mod, name = STDLIB_TYPE_MAPPING[canonical]
            tracker.need_stdlib(mod, name)
            return ast.Name(name)

        if rtype.isArray():
            inner = rtype.getComponentType()
            for _ in range(rtype.getArrayDimensions() - 1):
                inner = inner.getComponentType() if inner.isArray() else inner
            annotation = self._build_type_annotation(inner, tracker, own_package)
            for _ in range(rtype.getArrayDimensions()):
                annotation = ast.Subscript(ast.Name("list"), annotation)
            return annotation

        if rtype.isTypeVariable():
            return ast.Name(canonical)

        if rtype.isWildcard():
            upper = list(rtype.getUpperBounds())
            lower = list(rtype.getLowerBounds())
            if lower:
                return self._build_type_annotation(lower[0], tracker, own_package)
            if upper:
                return self._build_type_annotation(upper[0], tracker, own_package)
            tracker.need_typing("Any")
            return ast.Name("Any")

        if rtype.isParameterized():
            raw = rtype.getRawType()
            raw_canonical = raw.getCanonicalName()
            if raw_canonical in STDLIB_TYPE_MAPPING:
                mod, name = STDLIB_TYPE_MAPPING[raw_canonical]
                tracker.need_stdlib(mod, name)
                base = ast.Name(name)
            else:
                base = ast.Name(self._resolve_name(raw_canonical, tracker, own_package))
            type_args = list(rtype.getActualTypeArguments())
            if type_args:
                args = [self._build_type_annotation(a, tracker, own_package) for a in type_args]
                return ast.Subscript(base, ast.Tuple(args) if len(args) > 1 else args[0])
            return base

        return ast.Name(self._resolve_name(canonical, tracker, own_package))

    def _resolve_name(self, canonical: str, tracker: _ImportTracker, own_package: str) -> str:
        """Resolve a canonical Java name: register import if external, return short name."""
        if canonical in BASIC_TYPE_MAPPING:
            return BASIC_TYPE_MAPPING[canonical]
        parts = canonical.split(".")
        # Find first uppercase component (start of class name chain)
        for i, s in enumerate(parts):
            if s and s[0].isupper():
                pkg = ".".join(parts[:i])
                short = ".".join(parts[i:]).replace("$", ".")
                if pkg and pkg != own_package:
                    tracker.need_java(f"{pkg}.{parts[i]}")
                return short
        return parts[-1].replace("$", ".")

    def _build_type_params(self, type_vars: Any, tracker: _ImportTracker, own_package: str) -> list[ast.type_param]:
        result: list[ast.type_param] = []
        for tv in type_vars:
            bounds = list(tv.getBounds())
            if bounds:
                bound = self._build_type_annotation(bounds[0], tracker, own_package)
                result.append(ast.TypeVar(tv.getName(), bound=bound))
            else:
                result.append(ast.TypeVar(tv.getName()))
        return result

    def _determine_output_path(self, java_class_name: str) -> Path:
        parts = java_class_name.split(".")
        if len(parts) < 2:
            return self.output_dir / f"{java_class_name}.pyi"

        package_parts = parts[:-1]
        target = self.output_dir

        for i, part in enumerate(package_parts):
            target = target / part
            old_pyi = target.with_suffix(".pyi")
            is_flat = old_pyi.is_file()
            if is_flat and target.is_dir():
                _ = shutil.move(str(old_pyi), str(target / "__init__.pyi"))
            elif i < len(package_parts) - 1:
                target.mkdir(parents=True, exist_ok=True)
                if is_flat:
                    _ = shutil.move(str(old_pyi), str(target / "__init__.pyi"))

        if target.is_dir():
            return target / "__init__.pyi"
        return target.with_suffix(".pyi")


def _topo_sort(entries: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    """Topologically sort classes within a package file by intra-file dependencies.

    A class must appear after its superclass and implemented interfaces if they
    are also in the same batch (same output file).
    """
    # Map simple class name → entry (inner classes stripped via $)
    simple_to_entry: dict[str, tuple[str, Any]] = {}
    for name, rcls in entries:
        simple = name.rsplit(".", 1)[-1].split("$")[-1]
        simple_to_entry[simple] = (name, rcls)

    def deps_of(rcls: Any) -> list[str]:
        """Return simple names of in-batch bases."""
        result: list[str] = []
        sup = rcls.getGenericSuperclass()
        if sup is not None:
            cname = sup.getCanonicalName().rsplit(".", 1)[-1].split("$")[-1]
            if cname in simple_to_entry:
                result.append(cname)
        for iface in rcls.getGenericInterfaces():
            cname = iface.getCanonicalName().rsplit(".", 1)[-1].split("$")[-1]
            if cname in simple_to_entry:
                result.append(cname)
        return result

    # Kahn's algorithm
    in_degree: dict[str, int] = {name: 0 for name, _ in entries}
    dependents: dict[str, list[str]] = {name: [] for name, _ in entries}

    for name, rcls in entries:
        simple = name.rsplit(".", 1)[-1].split("$")[-1]
        for dep_simple in deps_of(rcls):
            dep_name = simple_to_entry[dep_simple][0]
            if dep_name in in_degree and dep_name != name:
                in_degree[name] += 1
                dependents[dep_name].append(name)

    queue: deque[str] = deque(name for name, deg in in_degree.items() if deg == 0)
    ordered_names: list[str] = []
    entry_map = dict(entries)

    while queue:
        node = queue.popleft()
        ordered_names.append(node)
        for dependent in dependents.get(node, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # Fall back to original order for any cycles
    seen = set(ordered_names)
    for name, _ in entries:
        if name not in seen:
            ordered_names.append(name)

    return [(name, entry_map[name]) for name in ordered_names]


def _parse_patch_stubs(snippets: list[str], tracker: _ImportTracker) -> list[ast.stmt]:
    """Parse patch snippet strings into AST function definitions.

    Snippets use bare type names (Iterator, Self, Any, etc.) — register their
    imports and return parsed ast.FunctionDef nodes.
    """
    results: list[ast.stmt] = []
    combined = " ".join(snippets)
    if "Iterator" in combined:
        tracker.need_stdlib("collections.abc", "Iterator")
    if "Self" in combined:
        tracker.need_typing("Self")
    if "Any" in combined:
        tracker.need_typing("Any")

    for snippet in snippets:
        src = f"def {snippet}" if not snippet.startswith("def ") else snippet
        # Wrap in a class so `return self` resolves
        try:
            tree = ast.parse(f"class _:\n    {src}", mode="exec")
            cls_body = tree.body[0]
            assert isinstance(cls_body, ast.ClassDef)
            results.extend(cls_body.body)
        except SyntaxError:
            logger.warning("Failed to parse patch snippet: %r", snippet)
    return results


def _is_stubgable(java_class_name: str) -> bool:
    """Return False for class names that cannot be represented as valid Python identifiers."""
    simple = java_class_name.rsplit(".", 1)[-1]
    # package-info, module-info, and any name with hyphens are invalid Python identifiers
    return simple.isidentifier() and not keyword.iskeyword(simple)


def _unify_imports(path: Path) -> None:
    """Rewrite a .pyi file so all import statements are deduplicated at the top."""
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    import_lines: list[str] = []
    other_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("from ") or stripped.startswith("import "):
            import_lines.append(stripped)
        else:
            other_lines.append(line)

    if not import_lines:
        return

    merged = _merge_from_imports(list(dict.fromkeys(import_lines)))
    body = "".join(other_lines).lstrip("\n")
    _ = path.write_text("\n".join(merged) + "\n\n" + body, encoding="utf-8")


def _merge_from_imports(import_lines: list[str]) -> list[str]:
    """Merge `from X import a, b` lines with the same module into one line."""
    order: list[str] = []
    by_module: dict[str, set[str]] = {}
    plain_imports: list[str] = []

    for line in import_lines:
        if line.startswith("from "):
            parts = line.split(" import ", 1)
            if len(parts) == 2:
                module = parts[0][5:].strip()
                names = {n.strip() for n in parts[1].split(",")}
                if module not in by_module:
                    order.append(module)
                    by_module[module] = set()
                by_module[module] |= names
                continue
        plain_imports.append(line)

    result = list(plain_imports)
    for module in order:
        names = sorted(by_module[module])
        result.append(f"from {module} import {', '.join(names)}")
    return result


def _merge_import_source(existing_imports: str, tracker: _ImportTracker) -> str:
    """Merge existing import text with new tracker imports, return unified import block."""
    new_lines = [ast.unparse(stmt) for stmt in tracker.build_imports()]
    existing_lines = [ln.strip() for ln in existing_imports.splitlines() if ln.strip()]
    all_imports = _merge_from_imports(list(dict.fromkeys(existing_lines + new_lines)))
    return "\n".join(all_imports) + "\n\n" if all_imports else ""
