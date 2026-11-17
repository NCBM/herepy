"""Check the Python half of HerePy against the facts its records claim, using the shipped interpreter.

    runs/client/python/bin/python3 tools/checks/check.py      # python.exe on Windows

The check runs without Minecraft: `java.lang` is stood in for, and everything else is the real package in the
runtime tree. Its cases are the ones the evidence table in `docs/adr/README.md` names, so a row there stays a claim
this file re-runs.

It is a script rather than a test suite: one list, no runner, no fixtures. It fails loudly the moment a decision
stops being true.
"""

import ast
import asyncio
from collections.abc import Callable
import importlib
import importlib.util
import json
import logging
import pathlib
import shutil
import sys
import tempfile
import types
import zipfile
import zipimport

CHECKS: list[tuple[str, Callable[[], None]]] = []


def check(what: str) -> Callable[[Callable[[], None]], Callable[[], None]]:
    """Register one case under the sentence it claims."""

    def register(fn: Callable[[], None]) -> Callable[[], None]:
        CHECKS.append((what, fn))
        return fn

    return register


def _stub_java() -> None:
    """`herecraft.api` imports `java.lang`, which only jep provides."""
    java = types.ModuleType("java")
    lang = types.ModuleType("java.lang")

    class _Object:
        pass

    lang.Object = _Object
    java.lang = lang
    sys.modules["java"] = java
    sys.modules["java.lang"] = lang


def _purge(name: str) -> None:
    """Drop a package and everything under it, the way a reload does."""
    for key in [key for key in sys.modules if key == name or key.startswith(name + ".")]:
        del sys.modules[key]


def _load_package(name: str, root: pathlib.Path):
    """A directory as a package: the shape ADR 0018 gives a script pack."""
    spec = importlib.util.spec_from_file_location(name, root / "__init__.py", submodule_search_locations=[str(root)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _raised(kind: type[BaseException], fn: Callable[[], object]) -> BaseException:
    """The exception ``fn`` raised, or a failure saying it did not raise one."""
    try:
        _ = fn()
    except kind as error:
        return error
    msg = f"{kind.__name__} was expected and nothing was raised"
    raise AssertionError(msg)


_stub_java()
logging.disable(logging.CRITICAL)

from herecraft import env
from herecraft import event as event_module
from herecraft.kernel import loader
from herecraft.kernel import unit as unit_module
from herecraft.manifest import ManifestError, read_archive, read_directory
from herecraft.stubgen import Overlay, StubGenerator, StubReport, closure, declared_seeds, write

WORK = pathlib.Path(tempfile.mkdtemp(prefix="herepy-check-"))
env.install("CLIENT", str(WORK))
MODS = WORK / "mods"
MODS.mkdir()


def _unit(name: str, body: str, api: str = "0.1") -> pathlib.Path:
    """One unit directory with a manifest and the body given."""
    root = MODS / name
    root.mkdir()
    manifest = f'id = "check/{name}"\nversion = "1"\napi = "{api}"\n'
    _ = (root / "manifest.toml").write_text(manifest, encoding="utf-8")
    _ = (root / "__init__.py").write_text(body, encoding="utf-8")
    return root


@check("a directory given a package name and a __path__ executes its __init__.py and serves submodules")
def directory_as_package() -> None:
    root = WORK / "pkg"
    root.mkdir()
    _ = (root / "__init__.py").write_text("from . import sub\nVALUE = 1\n", encoding="utf-8")
    _ = (root / "sub.py").write_text("VALUE = 'one'\n", encoding="utf-8")
    module = _load_package("check_pkg", root)
    assert module.VALUE == 1
    assert module.sub.VALUE == "one"
    assert pathlib.Path(module.sub.__file__) == root / "sub.py"


@check("a .pyz holding <name>/__init__.py imports through zipimport without touching sys.path")
def archive_as_package() -> None:
    archive = WORK / "pack.pyz"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("check_arch/__init__.py", "from . import sub\nVALUE = 2\n")
        zip_file.writestr("check_arch/sub.py", "VALUE = 'zip'\n")
    before = list(sys.path)
    spec = zipimport.zipimporter(str(archive)).find_spec("check_arch")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_arch"] = module
    spec.loader.exec_module(module)
    assert module.sub.VALUE == "zip"
    assert str(archive) in module.sub.__file__
    assert sys.path == before, "zipimport was not supposed to need sys.path"


@check("a .pyz whose root is the package root cannot be found by name")
def flat_archive() -> None:
    archive = WORK / "flat.pyz"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("__init__.py", "VALUE = 3\n")
    assert zipimport.zipimporter(str(archive)).find_spec("check_flat") is None


@check("an edit of the same byte size inside the same second is stale while the cache is kept")
def stale_pyc() -> None:
    root = WORK / "stale"
    root.mkdir()
    _ = (root / "__init__.py").write_text("from . import sub\n", encoding="utf-8")
    _ = (root / "sub.py").write_text("VALUE = 'one'\n", encoding="utf-8")
    assert _load_package("check_stale", root).sub.VALUE == "one"

    _ = (root / "sub.py").write_text("VALUE = 'two'\n", encoding="utf-8")
    _purge("check_stale")
    importlib.invalidate_caches()
    assert _load_package("check_stale", root).sub.VALUE == "one", "the cached bytecode was expected to be stale"


@check("clearing the cache before the reload makes that same edit visible")
def cache_cleared() -> None:
    root = WORK / "cleared"
    root.mkdir()
    _ = (root / "__init__.py").write_text("from . import sub\n", encoding="utf-8")
    _ = (root / "sub.py").write_text("VALUE = 'one'\n", encoding="utf-8")
    assert _load_package("check_cleared", root).sub.VALUE == "one"

    _ = (root / "sub.py").write_text("VALUE = 'two'\n", encoding="utf-8")
    _purge("check_cleared")
    shutil.rmtree(root / "__pycache__", ignore_errors=True)
    importlib.invalidate_caches()
    assert _load_package("check_cleared", root).sub.VALUE == "two"


@check("bytecode writing off from the first import makes that same edit visible")
def bytecode_off() -> None:
    root = WORK / "nosbytecode"
    root.mkdir()
    _ = (root / "__init__.py").write_text("from . import sub\n", encoding="utf-8")
    _ = (root / "sub.py").write_text("VALUE = 'one'\n", encoding="utf-8")
    sys.dont_write_bytecode = True
    try:
        assert _load_package("check_nobytecode", root).sub.VALUE == "one"
        assert not (root / "__pycache__").is_dir(), "no cache should have been written"
        _ = (root / "sub.py").write_text("VALUE = 'two'\n", encoding="utf-8")
        _purge("check_nobytecode")
        importlib.invalidate_caches()
        assert _load_package("check_nobytecode", root).sub.VALUE == "two"
    finally:
        sys.dont_write_bytecode = False


@check("discovery finds a unit directory and a .pyz, skips a broken manifest, and sorts by id")
def discovery() -> None:
    _unit("good", "VALUE = 'good'\n")
    (MODS / "broken").mkdir()
    _ = (MODS / "broken" / "manifest.toml").write_text(
        "id = 'no-namespace'\nversion = '1'\napi = '0.1'\n", encoding="utf-8"
    )
    archive = MODS / "archived.pyz"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            "herecraft_unit_check_archived/manifest.toml",
            'id = "check/archived"\nversion = "1"\napi = "0.1"\n',
        )
        zip_file.writestr("herecraft_unit_check_archived/__init__.py", "VALUE = 'archived'\n")
    ids = [source.manifest.id for source in loader.discover(MODS)]
    assert ids == sorted(ids), ids
    assert "check/good" in ids
    assert "check/archived" in ids
    assert all(unit_id != "check/broken" for unit_id in ids)


@check("an api mismatch is refused before the unit is imported")
def api_mismatch() -> None:
    root = _unit("future", "RAISED = True\n", api="9.9")
    error = _raised(ManifestError, lambda: loader.load(loader.UnitSource(root, read_directory(root), archive=False)))
    assert "9.9" in str(error), error
    assert "0.1" in str(error), error
    assert "herecraft_unit_check_future" not in sys.modules


@check("a unit that raises leaves no module behind")
def failed_load() -> None:
    root = _unit("exploding", "raise RuntimeError('boom')\n")
    error = _raised(RuntimeError, lambda: loader.load(loader.UnitSource(root, read_directory(root), archive=False)))
    assert "boom" in str(error), error
    assert "herecraft_unit_check_exploding" not in sys.modules


@check("an archive whose inner directory does not match its id is refused, naming both")
def archive_name_mismatch() -> None:
    archive = WORK / "mismatch.pyz"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("wrongname/manifest.toml", 'id = "check/mismatch"\nversion = "1"\napi = "0.1"\n')
        zip_file.writestr("wrongname/__init__.py", "")
    error = _raised(ManifestError, lambda: read_archive(archive))
    assert "wrongname" in str(error), error
    assert "herecraft_unit_check_mismatch" in str(error), error


CLIENT_BODY = (
    "from herecraft.markers import on_client\n"
    "CALLED = []\n"
    "\n"
    "@on_client\n"
    "def part() -> None:\n"
    "    CALLED.append('client')\n"
)


@check("@on_client runs where a client exists, and not on a dedicated server")
def client_marker() -> None:
    client_root = _unit("client_side", CLIENT_BODY)
    client = loader.load(loader.UnitSource(client_root, read_directory(client_root), archive=False))
    assert sys.modules[client.source.module_name].CALLED == ["client"]

    # One process is one distribution (ADR 0017), so the other case is simulated the only way it can be.
    env._installed = env.Dist.DEDICATED_SERVER  # the check reaches in; there is no supported second install
    try:
        server_root = _unit("server_side", CLIENT_BODY)
        server = loader.load(loader.UnitSource(server_root, read_directory(server_root), archive=False))
        assert sys.modules[server.source.module_name].CALLED == []
    finally:
        env._installed = env.Dist.CLIENT


@check("@on_server_start becomes a handler for ServerStartingEvent, handed the server rather than the event")
def server_marker() -> None:
    body = (
        "from herecraft.markers import on_server_start\n"
        "CALLED = []\n"
        "\n"
        "@on_server_start\n"
        "def part(server) -> None:\n"
        "    CALLED.append(server)\n"
    )
    root = _unit("server_start", body)
    source = loader.UnitSource(root, read_directory(root), archive=False)
    _ = loader.load(source)
    handlers = event_module._HANDLER_REGISTRY["net.neoforged.neoforge.event.server.ServerStartingEvent"]
    assert len(handlers) == 1, handlers

    class _Event:
        server = "a server"

    handlers[0].fn(_Event())
    assert sys.modules[source.module_name].CALLED == ["a server"]


class _CountingBus:
    """Stands in for Java's event bridge, so "the listener never left" is an observation and not a promise."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.trace: list[tuple[str, int]] = []

    def retain(self, java_class_name: str, needs_sync: bool) -> None:
        self.counts[java_class_name] = self.counts.get(java_class_name, 0) + 1
        self.trace.append(("retain", self.counts[java_class_name]))

    def release(self, java_class_name: str) -> None:
        self.counts[java_class_name] = self.counts.get(java_class_name, 0) - 1
        self.trace.append(("release", self.counts[java_class_name]))


@check("a reload keeps the listener on the bus and leaves only the new incarnation's handler")
def reload_swap() -> None:
    event_class = "net.neoforged.neoforge.event.server.ServerStoppingEvent"

    class _EventClass:
        __java_class_name__ = event_class
        __side__ = event_module.Side.BOTH

    bus = _CountingBus()
    event_module.bridge.install_bridge(bus)

    def incarnation(tag: str):
        with unit_module.active("local/scripts") as pack:

            def handler(_event) -> str:
                return tag

            event_module.listen(_EventClass, handler)
        pack.enable()
        return pack

    first = incarnation("first")
    asyncio.run(loader.replace(first, lambda: incarnation("second")))
    assert min(count for _, count in bus.trace) == 1, bus.trace
    handlers = event_module._HANDLER_REGISTRY[event_class]
    assert [handler.fn(None) for handler in handlers] == ["second"], handlers


@check("a command registered by a unit reaches the dispatcher, and goes when the unit does")
class _Dispatcher:
    """A stand-in for Java's command bridge: it keeps the paths it was told about and nothing else."""

    def __init__(self) -> None:
        self.declared: dict[str, int] = {}

    def declare(self, path: str, permission: int) -> None:
        self.declared[path] = permission

    def withdraw(self, path: str) -> None:
        _ = self.declared.pop(path, None)


def commands() -> None:
    from herecraft import commands as commands_module

    dispatcher = _Dispatcher()
    commands_module.install_commands(dispatcher)

    with unit_module.active("check/commander") as unit:
        commands_module.register("scriptive reload", lambda source: None)
        error = _raised(RuntimeError, lambda: commands_module.register("scriptive reload", lambda source: None))
        assert "already did" in str(error), error
    unit.enable()
    assert dispatcher.declared == {"scriptive reload": 2}, dispatcher.declared
    asyncio.run(unit.revoke_all())


class _Reflected:
    """A stand-in for a ReflectWrapper object, made of the callables the generator reads.

    The generator reaches Java through method names on these objects, so the same names answer from here and
    the renderer runs with no JVM under it.
    """

    def __init__(self, **members: object) -> None:
        for name, member in members.items():
            setattr(self, name, member)


class _Wrapper:
    """`ReflectWrapper.forClass`, answering from the classes the caller built."""

    def __init__(self, classes: dict[str, _Reflected]) -> None:
        self._classes = classes

    def forClass(self, clazz: object) -> object:
        return self._classes[str(clazz)]


class _Loader:
    """A classloader that answers with the name it was asked for."""

    def loadClass(self, name: str) -> str:
        return name


def _jty(**members: object) -> _Reflected:
    """A ReflectType stand-in: every question answered, so the walk may ask any of them."""
    defaults: dict[str, object] = {
        "getTypeName": lambda: "java.lang.Object",
        "getCanonicalName": lambda: "java.lang.Object",
        "isClass": lambda: True,
        "isParameterized": lambda: False,
        "isTypeVariable": lambda: False,
        "isArray": lambda: False,
        "isWildcard": lambda: False,
        "isPrimitive": lambda: False,
        "isVoid": lambda: False,
        "getRawType": lambda: None,
        "getActualTypeArguments": lambda: [],
        "getComponentType": lambda: None,
        "getUpperBounds": lambda: [],
        "getLowerBounds": lambda: [],
    }
    defaults.update(members)
    return _Reflected(**defaults)


def _jtype(canonical: str) -> _Reflected:
    """A plain class type, which names itself and nothing else."""
    return _jty(getTypeName=lambda: canonical, getCanonicalName=lambda: canonical)


def _as_type(value: str | _Reflected) -> _Reflected:
    """A type the caller wrote as a name, or one it built to carry type arguments or a component."""
    return value if isinstance(value, _Reflected) else _jtype(value)


def _jparameterized(raw: str, *arguments: _Reflected) -> _Reflected:
    """`List<Entry>`: the raw class and what the angle brackets carry."""
    return _jty(
        isParameterized=lambda: True,
        isClass=lambda: False,
        getTypeName=lambda: raw,
        getCanonicalName=lambda: raw,
        getRawType=lambda: _jtype(raw),
        getActualTypeArguments=lambda: list(arguments),
    )


def _jarray(component: _Reflected) -> _Reflected:
    """`Cell[]`: the component type is the class a stub names."""
    return _jty(isArray=lambda: True, isClass=lambda: False, getComponentType=lambda: component)


def _jwildcard(*upper: _Reflected, lower: tuple[_Reflected, ...] = ()) -> _Reflected:
    """`? extends Match`: the bound is the class a stub names."""
    return _jty(
        isWildcard=lambda: True,
        isClass=lambda: False,
        getUpperBounds=lambda: list(upper),
        getLowerBounds=lambda: list(lower),
    )


def _jtypevar(name: str, *bounds: _Reflected) -> _Reflected:
    """`T extends Bound`: a type variable names itself, and names its bound.

    Asked of a ReflectType the bound is `getUpperBounds`; asked of a ReflectTypeVariable — a class's or a
    method's own parameter — it is `getBounds`. Both answer here, so one stand-in serves either place.
    """
    return _jty(
        isTypeVariable=lambda: True,
        isClass=lambda: False,
        getTypeName=lambda: name,
        getBounds=lambda: list(bounds),
        getUpperBounds=lambda: list(bounds),
    )


def _jparam(index: int, canonical: str | _Reflected, vararg: bool = False) -> _Reflected:
    return _Reflected(
        getName=lambda: f"arg{index}",
        isNamePresent=lambda: False,
        isVarArg=lambda: vararg,
        getType=lambda: _as_type(canonical),
    )


def _jmethod(
    name: str,
    params: tuple[str | _Reflected, ...] = (),
    returns: str | _Reflected = "void",
    descriptor: str = "()V",
    *,
    static: bool = False,
    varargs: bool = False,
) -> _Reflected:
    return _Reflected(
        getName=lambda: name,
        getDescriptor=lambda: descriptor,
        isAbstract=lambda: False,
        isStatic=lambda: static,
        isFinal=lambda: False,
        getReturnType=lambda: _as_type(returns),
        getParameters=lambda: [
            _jparam(index, canonical, vararg=varargs and index == len(params) - 1)
            for index, canonical in enumerate(params)
        ],
        getTypeParameters=lambda: [],
    )


def _jconstructor(descriptor: str = "()V", params: tuple[str | _Reflected, ...] = ()) -> _Reflected:
    return _Reflected(
        getDescriptor=lambda: descriptor,
        getParameters=lambda: [_jparam(index, canonical) for index, canonical in enumerate(params)],
        getTypeParameters=lambda: [],
    )


def _jfield(name: str, canonical: str | _Reflected) -> _Reflected:
    return _Reflected(
        getName=lambda: name,
        isStatic=lambda: False,
        isFinal=lambda: True,
        getGenericType=lambda: _as_type(canonical),
    )


def _jclass(
    simple: str,
    *,
    package: str = "net.example",
    bases: tuple[str | _Reflected, ...] = (),
    methods: tuple[_Reflected, ...] = (),
    fields: tuple[_Reflected, ...] = (),
    constructors: tuple[_Reflected, ...] = (),
    inner: tuple[_Reflected, ...] = (),
    type_params: tuple[_Reflected, ...] = (),
) -> _Reflected:
    return _Reflected(
        getName=lambda: f"{package}.{simple}",
        getSimpleName=lambda: simple,
        getCanonicalName=lambda: f"{package}.{simple}",
        getPackageName=lambda: package,
        getGenericSuperclass=lambda: _as_type(bases[0]) if bases else None,
        getGenericInterfaces=lambda: [_as_type(base) for base in bases[1:]],
        getTypeParameters=lambda: list(type_params),
        getInnerClasses=lambda: list(inner),
        getMethods=lambda: list(methods),
        getFields=lambda: list(fields),
        getConstructors=lambda: list(constructors),
    )


def _jnested(outer: str, simple: str, *, fields: tuple[_Reflected, ...] = ()) -> _Reflected:
    """A nested class as `getInnerClasses` hands one over: its binary name, and what its members name."""
    return _Reflected(
        getName=lambda: f"{outer}${simple}",
        getSimpleName=lambda: simple,
        getCanonicalName=lambda: f"{outer}.{simple}",
        getPackageName=lambda: outer.rsplit(".", 1)[0],
        getGenericSuperclass=lambda: None,
        getGenericInterfaces=lambda: [],
        getTypeParameters=lambda: [],
        getInnerClasses=lambda: [],
        getMethods=lambda: [],
        getFields=lambda: list(fields),
        getConstructors=lambda: [],
    )


def _generate(
    root: pathlib.Path,
    classes: dict[str, _Reflected],
    *batches: tuple[str, ...],
    overlay: Overlay | None = None,
) -> StubReport:
    """Run the generator over the batches, on the fake classpath the caller built."""
    generator = StubGenerator(root, wrapper=_Wrapper(classes), classloader=_Loader(), overlay=overlay)
    report = StubReport()
    for names in batches:
        report.merge(generator.generate_batch(names))
    _ = generator.prune()
    return report


@check("a run over the same classes writes each class once, whatever the tree held before")
def stubs_are_idempotent() -> None:
    root = WORK / "stubs-twice"
    classes = {
        "net.example.Widget": _jclass("Widget", methods=(_jmethod("size", returns="int"),)),
        "net.example.Gadget": _jclass("Gadget", bases=("net.example.Widget",)),
    }
    names = tuple(classes)
    first = _generate(root, classes, names)
    written = (root / "net/example/__init__.pyi").read_text(encoding="utf-8")
    second = _generate(root, classes, names)
    assert (root / "net/example/__init__.pyi").read_text(encoding="utf-8") == written
    assert first.count("written") == 2, first.as_dict()
    assert second.count("written") == 2, second.as_dict()
    assert written.count("class Widget") == 1, written
    assert written.index("class Widget") < written.index("class Gadget"), written


@check("a class that leaves the set loses its stub, and every package on the path has an __init__.pyi")
def stubs_are_pruned() -> None:
    root = WORK / "stubs-pruned"
    classes = {"net.example.Widget": _jclass("Widget"), "net.other.Thing": _jclass("Thing", package="net.other")}
    _ = _generate(root, classes, tuple(classes))
    assert (root / "net/other/__init__.pyi").is_file()
    assert (root / "net/__init__.pyi").is_file(), "an intermediate package gets its own __init__.pyi"
    _ = _generate(root, classes, ("net.example.Widget",))
    assert not (root / "net/other").exists(), "a stub the run no longer produces is gone"
    assert (root / "net/example/__init__.pyi").is_file()


@check("a member no Python expression can spell is left out, and its class is written anyway")
def stub_omits_unnameable_members() -> None:
    root = WORK / "stubs-names"
    block = _jclass(
        "Block",
        methods=(_jmethod("neoforge$setValidBlocks", params=("java.util.Set",)), _jmethod("id", returns="int")),
        fields=(_jfield("neoforge$STATE", "java.lang.Object"), _jfield("NAME", "java.lang.String")),
    )
    report = _generate(root, {"net.example.Block": block}, ("net.example.Block",))
    source = (root / "net/example/__init__.pyi").read_text(encoding="utf-8")
    _ = ast.parse(source)  # what the run wrote is Python
    assert "class Block" in source, source
    assert "def id(" in source, source
    assert "neoforge" not in source, source
    outcome = report.outcomes["net.example.Block"]
    assert outcome.status == "written", outcome
    assert outcome.omitted == ("neoforge$STATE", "neoforge$setValidBlocks"), outcome


@check("a class name no import can spell is reported as rejected, and nothing is written for it")
def stub_rejects_unspellable_names() -> None:
    root = WORK / "stubs-reject"
    report = _generate(root, {}, ("net.example.Outer$Inner", "net.example.package-info"))
    outcome = report.outcomes["net.example.Outer$Inner"]
    assert outcome.status == "rejected", outcome
    assert "identifier" in (outcome.reason or ""), outcome
    assert report.outcomes["net.example.package-info"].status == "rejected", report.as_dict()
    assert not list(root.rglob("*.pyi")), "a rejected name writes nothing"


@check("a javadoc fragment becomes the text a docstring shows, markup included")
def javadoc_markup() -> None:
    from herecraft.stubgen.javadoc import to_text

    assert to_text(["Represents an OpenAL audio channel."]) == "Represents an OpenAL audio channel."
    assert to_text(["Uses {@code DEBUG_} flags and {@literal <T>}."]) == "Uses `DEBUG_` flags and `<T>`."
    assert to_text(["{@link net.minecraft.core.Registry#CUSTOM_STAT a custom type} and {@link CustomStat}."]) == (
        "a custom type and CustomStat."
    )
    assert to_text(["{@link #isKeyDown()} asks the same."]) == "isKeyDown() asks the same."
    assert to_text(["<p>One.</p><p><strong>Two</strong> and <em>three</em>.</p>"]) == "One.\n\n**Two** and *three*."
    assert to_text(["Reads:", "<ul><li>first</li><li>second</li></ul>"]) == "Reads:\n\n- first\n- second"
    assert to_text(["<table><tr><th>a</th><td>b</td></tr></table>"]) == "a | b"
    assert to_text(["5 &lt; 7 &amp; 9"]) == "5 < 7 & 9"
    assert to_text(["Only tags:", "@param <T> a value", "@see Something"]) == "Only tags:"
    assert to_text(["Spells <T> as a type parameter."]) == "Spells <T> as a type parameter."


@check("a stub carries the docstring the data holds, once per overload")
def stub_docstrings() -> None:
    root = WORK / "stubs-docs"
    widget = _jclass(
        "Widget",
        methods=(
            _jmethod("size", returns="int", descriptor="()I"),
            _jmethod("make", params=("int",), returns="Widget", descriptor="(I)Lnet/example/Widget;"),
            _jmethod(
                "make",
                params=("java.lang.String",),
                returns="Widget",
                descriptor="(Ljava/lang/String;)Lnet/example/Widget;",
            ),
        ),
        constructors=(_jconstructor("()V"), _jconstructor("(I)V")),
    )
    overlay = Overlay(
        {
            "source": {"artifact": "parchment"},
            "classes": {
                "net.example.Widget": {
                    "javadoc": ["A widget the game owns.", "<p>Second paragraph.</p>"],
                    "methods": [
                        {"name": "size", "descriptor": "()I", "javadoc": ["How big it is."]},
                        {
                            "name": "make",
                            "descriptor": "(I)Lnet/example/Widget;",
                            "javadoc": ["Build one from a count."],
                        },
                        {"name": "<init>", "descriptor": "(I)V", "javadoc": ["Build one."]},
                        {"name": "make", "descriptor": "(Ljava/lang/String;)Lnet/example/Widget;"},
                    ],
                }
            },
        }
    )
    _ = _generate(root, {"net.example.Widget": widget}, ("net.example.Widget",), overlay=overlay)
    source = (root / "net/example/__init__.pyi").read_text(encoding="utf-8")
    parsed = ast.parse(source)
    widget_def = next(node for node in parsed.body if isinstance(node, ast.ClassDef))
    assert widget_def.body[0].value.value == "A widget the game owns.\n\nSecond paragraph.", widget_def.body[0]

    documented = [stmt for stmt in ast.walk(widget_def) if isinstance(stmt, ast.FunctionDef) and stmt.body[0].value]
    written = [stmt.body[0].value.value for stmt in documented if isinstance(stmt.body[0].value, ast.Constant)]
    assert written.count("How big it is.") == 1, written
    assert written.count("Build one from a count.") == 1, written
    assert written.count("Build one.") == 1, written
    assert source.count("Build one from a count.") == 1, "an overload carries the doc once"


@check("with no data, a stub carries no docstring at all")
def stub_without_docs() -> None:
    root = WORK / "stubs-nodocs"
    widget = _jclass("Widget", methods=(_jmethod("size", returns="int"),))
    _ = _generate(root, {"net.example.Widget": widget}, ("net.example.Widget",))
    source = (root / "net/example/__init__.pyi").read_text(encoding="utf-8")
    widget_def = next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef))
    assert not any(isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) for stmt in widget_def.body)

    empty = Overlay({"classes": {}})
    assert empty.class_doc("net.example.Widget") == ""
    assert empty.method_doc("net.example.Widget", "size", "()I") == ""
    assert empty.parameter_names("net.example.Widget", "size", "()I") == {}


@check("a parameter takes the name the data gives its slot, and keeps argN where the data has none")
def stub_parameter_names() -> None:
    root = WORK / "stubs-params"
    widget = _jclass(
        "Widget",
        methods=(
            _jmethod(
                "place",
                params=("int", "double", "long", "java.lang.String"),
                descriptor="(IDJLjava/lang/String;)V",
            ),
            _jmethod("sum", params=("long",), varargs=True, returns="long", descriptor="([J)J"),
            _jmethod("only", params=("int", "int"), descriptor="(II)V"),
            _jmethod("described", static=True, params=("int",), descriptor="(I)V"),
        ),
        constructors=(_jconstructor("(DJ)V", ("double", "long")),),
    )
    overlay = Overlay(
        {
            "classes": {
                "net.example.Widget": {
                    "methods": [
                        {
                            "name": "place",
                            "descriptor": "(IDJLjava/lang/String;)V",
                            "parameters": [
                                {"index": 1, "name": "x"},
                                {"index": 2, "name": "y"},
                                {"index": 4, "name": "z"},
                                {"index": 6, "name": "label"},
                            ],
                        },
                        {
                            "name": "sum",
                            "descriptor": "([J)J",
                            "parameters": [{"index": 1, "name": "values"}],
                        },
                        {"name": "only", "descriptor": "(II)V", "parameters": [{"index": 1, "name": "count"}]},
                        {"name": "described", "descriptor": "(I)V", "parameters": [{"index": 0, "name": "size"}]},
                        {
                            "name": "<init>",
                            "descriptor": "(DJ)V",
                            "parameters": [{"index": 1, "name": "x"}, {"index": 3, "name": "y"}],
                        },
                    ]
                }
            }
        }
    )
    report = _generate(root, {"net.example.Widget": widget}, ("net.example.Widget",), overlay=overlay)
    source = (root / "net/example/__init__.pyi").read_text(encoding="utf-8")
    widget_def = next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef))
    arguments = {
        node.name: [arg.arg for arg in node.args.posonlyargs]
        + ([node.args.vararg.arg] if node.args.vararg is not None else [])
        for node in widget_def.body
        if isinstance(node, ast.FunctionDef)
    }
    assert arguments["place"] == ["self", "x", "y", "z", "label"], arguments["place"]
    assert arguments["sum"] == ["self", "values"], "a varargs parameter is one slot, whatever its component is"
    assert arguments["only"] == ["self", "count", "arg1"], "what the data does not cover stays argN"
    assert arguments["described"] == ["size"], "a static member starts at slot 0"
    assert arguments["__init__"] == ["self", "x", "y"], arguments["__init__"]
    assert report.named == 9, report.as_dict()["applied"]


@check("the corpus is what the seeds reach, transitively, and nothing else")
def surface_closure() -> None:
    classes = {
        "net.example.Widget": _jclass(
            "Widget",
            bases=("net.example.Base",),
            fields=(_jfield("label", "net.example.Label"),),
            methods=(_jmethod("at", returns="net.example.Pos"),),
        ),
        "net.example.Base": _jclass("Base"),
        "net.example.Label": _jclass("Label"),
        "net.example.Pos": _jclass("Pos", fields=(_jfield("world", "net.example.World"),)),
        "net.example.World": _jclass("World"),
        "net.example.Unreached": _jclass("Unreached"),
    }
    reach = closure(("net.example.Widget",), wrapper=_Wrapper(classes), classloader=_Loader())
    assert reach.classes == (
        "net.example.Base",
        "net.example.Label",
        "net.example.Pos",
        "net.example.Widget",
        "net.example.World",
    ), reach.classes
    assert not reach.missing, reach.missing


@check("a type argument, an array component, a wildcard bound and a type parameter bound each bring a class")
def surface_closure_types() -> None:
    classes = {
        "net.example.Widget": _jclass(
            "Widget",
            type_params=(_jtypevar("T", _jtype("net.example.Bound")),),
            methods=(
                _jmethod("entries", returns=_jparameterized("java.util.List", _jtype("net.example.Entry"))),
                _jmethod("cells", params=(_jarray(_jtype("net.example.Cell")),)),
                _jmethod("match", returns=_jwildcard(_jtype("net.example.Match"))),
                _jmethod("value", returns=_jtypevar("V", _jtype("net.example.Value"))),
            ),
            fields=(
                _jfield(
                    "names",
                    _jparameterized("java.util.Map", _jtype("java.lang.String"), _jtype("net.example.Name")),
                ),
            ),
        ),
    }
    for simple in ("Bound", "Entry", "Cell", "Match", "Value", "Name"):
        classes[f"net.example.{simple}"] = _jclass(simple)
    reach = closure(("net.example.Widget",), wrapper=_Wrapper(classes), classloader=_Loader())
    assert reach.classes == (
        "net.example.Bound",
        "net.example.Cell",
        "net.example.Entry",
        "net.example.Match",
        "net.example.Name",
        "net.example.Value",
        "net.example.Widget",
    ), reach.classes
    assert not reach.missing, reach.missing


@check("a name that carries a nested class renders the class that declares it, seed or reference")
def surface_closure_nested() -> None:
    nested = _jnested("net.example.Event", "Break", fields=(_jfield("cause", "net.example.Cause"),))
    classes = {
        "net.example.Widget": _jclass("Widget", fields=(_jfield("evt", "net.example.Event$Break"),)),
        "net.example.Event": _jclass("Event", inner=(nested,)),
        "net.example.Event$Break": nested,
        "net.example.Cause": _jclass("Cause"),
    }
    reach = closure(("net.example.Widget",), wrapper=_Wrapper(classes), classloader=_Loader())
    assert reach.classes == ("net.example.Cause", "net.example.Event", "net.example.Widget"), reach.classes
    seeded = closure(("net.example.Event$Break",), wrapper=_Wrapper(classes), classloader=_Loader())
    assert seeded.classes == ("net.example.Cause", "net.example.Event"), seeded.classes


@check("a class the loader does not have is reported, and a cycle in the graph ends")
def surface_closure_gaps() -> None:
    classes = {
        "net.example.Widget": _jclass(
            "Widget",
            fields=(_jfield("gone", "net.example.Gone"), _jfield("peer", "net.example.Peer")),
        ),
        "net.example.Peer": _jclass("Peer", methods=(_jmethod("widget", returns="net.example.Widget"),)),
    }
    reach = closure(("net.example.Widget",), wrapper=_Wrapper(classes), classloader=_Loader())
    assert reach.classes == ("net.example.Peer", "net.example.Widget"), reach.classes
    assert set(reach.missing) == {"net.example.Gone"}, reach.missing
    assert "KeyError" in reach.missing["net.example.Gone"], reach.missing


@check("a run renders the surface it is given, and the tree holds no class it did not reach")
def surface_run_selects_the_corpus() -> None:
    root = WORK / "stubs-surface"
    classes = {
        "net.example.Widget": _jclass(
            "Widget",
            bases=("net.example.Base",),
            fields=(_jfield("gone", "net.example.Gone"),),
        ),
        "net.example.Base": _jclass("Base"),
        "net.other.Stray": _jclass("Stray", package="net.other"),
    }
    generator = StubGenerator(root, wrapper=_Wrapper(classes), classloader=_Loader())
    report = generator.generate_surface(("net.example.Widget",))
    _ = generator.prune()
    assert (root / "net/example/__init__.pyi").is_file()
    assert not (root / "net/other").exists(), "a class nothing reaches has no stub"
    assert sorted(report.outcomes) == ["net.example.Base", "net.example.Gone", "net.example.Widget"], report.as_dict()
    assert report.outcomes["net.example.Gone"].status == "failed", report.as_dict()
    assert "cannot be reached" in (report.outcomes["net.example.Gone"].reason or ""), report.as_dict()


@check("the seeds are the names herecraft/api declares, the event wrappers among them")
def surface_seeds() -> None:
    seeds = declared_seeds()
    assert "net.neoforged.neoforge.event.server.ServerStartingEvent" in seeds, seeds
    assert "net.neoforged.neoforge.event.level.BlockEvent$BreakEvent" in seeds, seeds
    assert seeds == sorted(set(seeds)), seeds


@check("a package that holds no class of its own holds only the marker, whatever an earlier run left there")
def stale_package_marker_is_replaced() -> None:
    root = WORK / "stubs-marker"
    marker = root / "net/other/__init__.pyi"
    marker.parent.mkdir(parents=True)
    _ = marker.write_text("class Leftover: ...\n", encoding="utf-8")
    classes = {"net.other.deep.Thing": _jclass("Thing", package="net.other.deep")}
    _ = _generate(root, classes, ("net.other.deep.Thing",))
    assert marker.read_text(encoding="utf-8") == "", "a package above the classes is a marker and nothing else"
    assert (root / "net/other/deep/__init__.pyi").is_file()
    _ = _generate(root, classes, ("net.other.deep.Thing",))
    assert marker.read_text(encoding="utf-8") == "", marker.read_text(encoding="utf-8")


@check("the bytes belong to the class, whatever order the reflection answered in")
def stubs_ignore_reflection_order() -> None:
    root = WORK / "stubs-order"
    methods = (
        _jmethod("alpha", returns="int", descriptor="()I"),
        _jmethod("beta", params=("int",), descriptor="(I)V"),
        _jmethod("beta", params=("java.lang.String",), descriptor="(Ljava/lang/String;)V"),
    )
    fields = (_jfield("ZED", "int"), _jfield("ABLE", "java.lang.String"))
    forward = {
        "net.example.Widget": _jclass("Widget", methods=methods, fields=fields),
        "net.example.Gadget": _jclass("Gadget", bases=("net.example.Widget",)),
    }
    backward = {
        "net.example.Gadget": _jclass("Gadget", bases=("net.example.Widget",)),
        "net.example.Widget": _jclass("Widget", methods=tuple(reversed(methods)), fields=tuple(reversed(fields))),
    }
    _ = _generate(root, forward, tuple(forward))
    first = (root / "net/example/__init__.pyi").read_text(encoding="utf-8")
    _ = _generate(root, backward, tuple(backward))
    second = (root / "net/example/__init__.pyi").read_text(encoding="utf-8")
    assert first == second, "a class's bytes come from the class, not from the order reflection answered in"


@check("a run writes the corpus and its report, and answers what it pruned")
def run_writes_the_corpus() -> None:
    root = WORK / "stubs-run"
    stale = root / "net/other/__init__.pyi"
    stale.parent.mkdir(parents=True)
    _ = stale.write_text("class Gone: ...\n", encoding="utf-8")
    classes = {
        "net.example.Gadget": _jclass("Gadget"),
        "net.example.Widget": _jclass("Widget", bases=("net.example.Gadget",)),
    }
    report, pruned = write(("net.example.Widget",), root, wrapper=_Wrapper(classes), classloader=_Loader())
    assert pruned == 1, pruned
    assert report.count("written") == 2, report.as_dict()
    assert (root / "net/example/__init__.pyi").is_file()
    assert not (root / "net/other").exists(), "a run prunes what it did not produce"
    saved = json.loads((root / "stubgen-report.json").read_text(encoding="utf-8"))
    assert saved["summary"] == {"written": 2, "rejected": 0, "failed": 0}, saved["summary"]
    assert saved["applied"] == {"parameters": 0, "docstrings": 0}, saved["applied"]


@check("the stubgen unit declares its command, and its manifest names the directory it sits in")
def stubgen_unit() -> None:
    from herecraft import commands as commands_module

    root = pathlib.Path("src/units/stubgen")
    manifest = read_directory(root)
    assert manifest.id == "herepy/stubgen", manifest.id
    dispatcher = _Dispatcher()
    commands_module.install_commands(dispatcher)
    with unit_module.active(manifest.id):
        _ = _load_package(manifest.module_name, root)
    try:
        assert dispatcher.declared == {"stubgen write": 2}, dispatcher.declared
    finally:
        _purge(manifest.module_name)


def main() -> int:
    failures = 0
    for what, case in CHECKS:
        try:
            case()
        except Exception as error:  # a check reports whatever went wrong, including AssertionError
            failures += 1
            print(f"FAIL {what}\n     {type(error).__name__}: {error}")
        else:
            print(f"ok   {what}")
    print(f"\n{len(CHECKS) - failures} of {len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
