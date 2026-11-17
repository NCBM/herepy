"""herecraft.stubgen.core — Generate Python .pyi stubs from Java classes via ReflectWrapper."""

from __future__ import annotations

import ast
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
import keyword
from logging import getLogger
from pathlib import Path
from typing import Any, Final, Literal

from .overlay import CONSTRUCTOR, Overlay

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


@dataclass(frozen=True)
class Outcome:
    """What became of one Java class name."""

    status: Literal["written", "rejected", "failed"]
    path: Path | None = None
    reason: str | None = None
    omitted: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"status": self.status}
        if self.path is not None:
            data["path"] = str(self.path)
        if self.reason is not None:
            data["reason"] = self.reason
        if self.omitted:
            data["omitted"] = list(self.omitted)
        return data


class StubReport:
    """What a run decided, class by class — the JSON the run leaves beside the stubs."""

    def __init__(self) -> None:
        self.outcomes: dict[str, Outcome] = {}

    def record(self, name: str, outcome: Outcome) -> None:
        self.outcomes[name] = outcome

    def update(self, outcomes: dict[str, Outcome]) -> None:
        self.outcomes.update(outcomes)

    def count(self, status: str) -> int:
        return sum(1 for outcome in self.outcomes.values() if outcome.status == status)

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": {status: self.count(status) for status in ("written", "rejected", "failed")},
            "classes": {name: self.outcomes[name].as_dict() for name in sorted(self.outcomes)},
        }


class _Module:
    """One output file: the classes that belong in it, and the imports they need."""

    tracker: _ImportTracker
    classes: dict[str, ast.ClassDef]

    def __init__(self) -> None:
        self.tracker = _ImportTracker()
        self.classes = {}


class StubGenerator:
    """Generates Python .pyi stub files from Java classes via ReflectWrapper."""

    output_dir: Path

    def __init__(
        self,
        output_dir: str | Path,
        *,
        wrapper: type[Any] | None = None,
        classloader: Any = None,
        overlay: Overlay | None = None,
    ) -> None:
        """`wrapper` and `classloader` are what the reflection reaches through; both default to the game's.

        `overlay` is the data the class files do not carry: parameter names and docstrings (ADR 0021).
        """
        self.output_dir = Path(output_dir)
        if wrapper is None:
            from herecraft._internals.javans import ReflectWrapper

            wrapper = ReflectWrapper
        # The context loader sees the classes mod loaders define as well as the JDK's
        if classloader is None:
            from java.lang import Thread

            classloader = Thread.currentThread().getContextClassLoader()
        self._wrapper: type[Any] = wrapper
        self._classloader: Any = classloader
        self._overlay: Overlay | None = overlay
        self._modules: dict[Path, _Module] = {}
        self._written: set[Path] = set()

    def _load_class(self, java_class_name: str) -> Any:
        """Load a Java class using the stored classloader."""
        return self._classloader.loadClass(java_class_name)

    def generate(self, java_class_name: str) -> StubReport:
        """Generate the stub for one Java class."""
        return self.generate_batch([java_class_name])

    def generate_batch(self, class_names: Iterable[str]) -> StubReport:
        """Reflect every class, then render each module its classes name, whole.

        A batch writes the modules it reaches. A later batch that reaches one of them again renders it from
        every class the generator has seen, so a run's output stays a function of the names it was given.
        """
        report = StubReport()
        reflected: dict[str, Any] = {}
        for name in class_names:
            if not _is_stubgable(name):
                report.record(name, Outcome("rejected", reason="the name is not a Python identifier"))
                continue
            try:
                reflected[name] = self._wrapper.forClass(self._load_class(name))
            except Exception as error:
                logger.warning("Failed to reflect %s: %s", name, error)
                report.record(name, Outcome("failed", reason=f"{type(error).__name__}: {error}"))

        by_file: dict[Path, list[tuple[str, Any]]] = {}
        for name, rcls in reflected.items():
            by_file.setdefault(_output_path(self.output_dir, name), []).append((name, rcls))

        for path, entries in by_file.items():
            module = self._modules.setdefault(path, _Module())
            outcomes: dict[str, Outcome] = {}
            for name, rcls in _topo_sort(entries):
                class_def = self._build_class(rcls, module.tracker, rcls.getPackageName())
                module.classes[name] = class_def
                outcomes[name] = Outcome("written", path, omitted=_drop_unnameable(class_def))

            problem = self._write_module(path, module)
            if problem is not None:
                logger.warning("%s was left unwritten: %s", path, problem)
                report.update({name: Outcome("failed", path, reason=problem) for name in outcomes})
                continue
            for name in outcomes:
                logger.info("Generated stub: %s -> %s", name, path)
            report.update(outcomes)

        return report

    def _write_module(self, path: Path, module: _Module) -> str | None:
        """Render a module whole and write it, or say why it was not written."""
        source = _render(module)
        problem = _unwritable(source)
        if problem is not None:
            return problem
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(source, encoding="utf-8")
        self._written.add(path)
        parent = path.parent
        while parent != self.output_dir and self.output_dir in parent.parents:
            init = parent / "__init__.pyi"
            if not init.exists():
                _ = init.write_text("", encoding="utf-8")
            self._written.add(init)
            parent = parent.parent
        return None

    def prune(self) -> int:
        """Remove the stubs this run did not write, and the directories that leaves empty."""
        removed = 0
        for stale in sorted(self.output_dir.rglob("*.pyi")):
            if stale not in self._written:
                stale.unlink()
                removed += 1
        for directory in sorted((path for path in self.output_dir.rglob("*") if path.is_dir()), reverse=True):
            if not any(directory.iterdir()):
                directory.rmdir()
        if removed:
            logger.info("Pruned %d stubs the run no longer produces", removed)
        return removed

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
            body.extend(self._build_method(rcls.getName(), methods, tracker, own_package))

        constructors = list(rcls.getConstructors())
        if constructors:
            body.extend(self._build_constructor(rcls.getName(), constructors, tracker, own_package))

        # Inject JEP-provided dunder methods for patched interfaces
        canonical = rcls.getCanonicalName()
        if canonical in INTERFACE_PATCH:
            body.extend(_parse_patch_stubs(INTERFACE_PATCH[canonical], tracker))

        if not body:
            body.append(ast.Expr(ast.Constant(...)))

        doc = self._class_doc(rcls)
        if doc:
            body.insert(0, _docstring(doc))

        return ast.ClassDef(
            name=class_name,
            bases=bases,
            keywords=[],
            body=body,
            decorator_list=[],
            type_params=type_params,
        )

    def _class_doc(self, rcls: Any) -> str:
        """The class's docstring text from the overlay, or "" when the data does not carry one."""
        return self._overlay.class_doc(rcls.getName()) if self._overlay is not None else ""

    def _method_doc(self, owner: str, member: Any, name: str) -> str:
        """A method's or constructor's docstring text, keyed by the name the data uses for it."""
        if self._overlay is None:
            return ""
        return self._overlay.method_doc(owner, name, member.getDescriptor())

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

    def _build_method(
        self, owner: str, methods: list[Any], tracker: _ImportTracker, own_package: str
    ) -> list[ast.FunctionDef]:
        result: list[ast.FunctionDef] = []
        has_overload = len(methods) > 1
        documented: set[str] = set()

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

            body: list[ast.stmt] = []
            doc = self._method_doc(owner, m, m.getName())
            if doc and doc not in documented:
                documented.add(doc)
                body.append(_docstring(doc))
            body.append(ast.Expr(ast.Constant(...)))

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
                    body=body,
                    decorator_list=decorators,
                    returns=returns,
                    type_params=type_params,
                )
            )

        return result

    def _build_constructor(
        self, owner: str, constructors: list[Any], tracker: _ImportTracker, own_package: str
    ) -> list[ast.FunctionDef]:
        result: list[ast.FunctionDef] = []
        has_overload = len(constructors) > 1
        documented = False

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

            body: list[ast.stmt] = []
            if not documented:
                doc = self._method_doc(owner, ctor, CONSTRUCTOR)
                if doc:
                    documented = True
                    body.append(_docstring(doc))
            body.append(ast.Expr(ast.Constant(...)))

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
                    body=body,
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


def _output_path(output_dir: Path, java_class_name: str) -> Path:
    """The module a class belongs to: a package's `__init__.pyi`, or `<name>.pyi` in the root package."""
    package = java_class_name.split(".")[:-1]
    if not package:
        return output_dir / f"{java_class_name}.pyi"
    return output_dir.joinpath(*package, "__init__.pyi")


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


def _docstring(text: str) -> ast.Expr:
    """A docstring: the first statement of a class or of a function."""
    return ast.Expr(ast.Constant(text))


def _render(module: _Module) -> str:
    """The whole module: the imports its classes need, then the classes themselves."""
    body: list[ast.stmt] = [*module.tracker.build_imports(), *module.classes.values()]
    return ast.unparse(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))) + "\n"


def _unwritable(source: str) -> str | None:
    """Why an assembled module cannot be written, or None when it parses and its names are spellable."""
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return f"line {error.lineno}: {error.msg}"
    return next(
        (f"{name} is not a Python identifier" for name in _written_names(tree) if not name.isidentifier()), None
    )


def _written_names(tree: ast.AST) -> Iterator[str]:
    """Every name the module declares, a nested class's members included."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.name
        elif isinstance(node, ast.arg):
            yield node.arg
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            yield node.target.id


def _drop_unnameable(class_def: ast.ClassDef) -> tuple[str, ...]:
    """Leave out the members no Python expression can spell, and name what was left out."""
    omitted: list[str] = []
    kept: list[ast.stmt] = []
    for stmt in class_def.body:
        unspellable = [name for name in _declared_names(stmt) if not name.isidentifier()]
        if unspellable:
            omitted.extend(unspellable)
            continue
        if isinstance(stmt, ast.ClassDef):
            omitted.extend(_drop_unnameable(stmt))
        kept.append(stmt)
    class_def.body = kept or [ast.Expr(ast.Constant(...))]
    return tuple(omitted)


def _declared_names(stmt: ast.stmt) -> list[str]:
    """The names one statement declares, without descending into a nested class."""
    if isinstance(stmt, ast.ClassDef):
        return [stmt.name]
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return [stmt.name, *_argument_names(stmt.args)]
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        return [stmt.target.id]
    return []


def _argument_names(args: ast.arguments) -> list[str]:
    names = [arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
    names.extend(arg.arg for arg in (args.vararg, args.kwarg) if arg is not None)
    return names
