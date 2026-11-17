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
from herecraft.stubgen import StubGenerator, StubReport

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
def commands() -> None:
    from herecraft import commands as commands_module

    class _Dispatcher:
        def __init__(self) -> None:
            self.declared: dict[str, int] = {}

        def declare(self, path: str, permission: int) -> None:
            self.declared[path] = permission

        def withdraw(self, path: str) -> None:
            _ = self.declared.pop(path, None)

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


def _jtype(canonical: str) -> _Reflected:
    return _Reflected(
        getCanonicalName=lambda: canonical,
        isArray=lambda: False,
        isTypeVariable=lambda: False,
        isWildcard=lambda: False,
        isParameterized=lambda: False,
    )


def _jparam(index: int, canonical: str) -> _Reflected:
    return _Reflected(
        getName=lambda: f"arg{index}",
        isNamePresent=lambda: False,
        isVarArg=lambda: False,
        getType=lambda: _jtype(canonical),
    )


def _jmethod(name: str, params: tuple[str, ...] = (), returns: str = "void") -> _Reflected:
    return _Reflected(
        getName=lambda: name,
        isAbstract=lambda: False,
        isStatic=lambda: False,
        isFinal=lambda: False,
        getReturnType=lambda: _jtype(returns),
        getParameters=lambda: [_jparam(index, canonical) for index, canonical in enumerate(params)],
        getTypeParameters=lambda: [],
    )


def _jfield(name: str, canonical: str) -> _Reflected:
    return _Reflected(
        getName=lambda: name,
        isStatic=lambda: False,
        isFinal=lambda: True,
        getGenericType=lambda: _jtype(canonical),
    )


def _jclass(
    simple: str,
    *,
    package: str = "net.example",
    bases: tuple[str, ...] = (),
    methods: tuple[_Reflected, ...] = (),
    fields: tuple[_Reflected, ...] = (),
) -> _Reflected:
    return _Reflected(
        getSimpleName=lambda: simple,
        getCanonicalName=lambda: f"{package}.{simple}",
        getPackageName=lambda: package,
        getGenericSuperclass=lambda: _jtype(bases[0]) if bases else None,
        getGenericInterfaces=lambda: [_jtype(base) for base in bases[1:]],
        getTypeParameters=lambda: [],
        getInnerClasses=lambda: [],
        getMethods=lambda: list(methods),
        getFields=lambda: list(fields),
        getConstructors=lambda: [],
    )


def _generate(root: pathlib.Path, classes: dict[str, _Reflected], *batches: tuple[str, ...]) -> StubReport:
    """Run the generator over the batches, on the fake classpath the caller built."""
    generator = StubGenerator(root, wrapper=_Wrapper(classes), classloader=_Loader())
    report = StubReport()
    for names in batches:
        report.update(generator.generate_batch(names).outcomes)
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
