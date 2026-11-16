"""Check the Python half of HerePy against the facts its records claim, using the shipped interpreter.

    runs/client/python/bin/python3.13 tools/checks/check.py      # python.exe on Windows

The check runs without Minecraft: `java.lang` is stood in for, and everything else is the real package in the
runtime tree. Its cases are the ones the evidence table in `docs/adr/README.md` names, so a row there stays a claim
this file re-runs.

It is a script rather than a test suite: one list, no runner, no fixtures. It fails loudly the moment a decision
stops being true.
"""

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
    assert dispatcher.declared == {}, dispatcher.declared


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
