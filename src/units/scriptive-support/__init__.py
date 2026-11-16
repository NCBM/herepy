"""The script track: one package at the game directory's `python/scripts`, imported as a single unit.

The pack is a package like any other (ADR 0018): its `__init__.py` is the entry, submodules and relative imports
work, and the whole pack is one unit, so what any of it registers is taken back together. Bytecode writing is
switched off, because the measured failure is an edit that keeps a file's byte size inside the same second being
served from a stale `.pyc`.

Reloading belongs to this unit: it drops the pack's modules from `sys.modules`, imports it again, and swaps it in
through the kernel, which keeps the bus populated across the exchange. The command is its own — `/scriptive reload`
— because the core knows nothing about scripts.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path
import sys
from typing import Any

from herecraft import env
from herecraft.api.core import Component
from herecraft.commands import command
from herecraft.kernel import active, loader
from herecraft.markers import on_server_start

logger = logging.getLogger("herecraft.scriptive")

PACKAGE = "herecraft_scripts"
IDENTITY = "local/scripts"
ROOT = Path("python") / "scripts"
ENTRY = "__init__.py"


def _pack_root() -> Path | None:
    """The pack's directory, or ``None`` with one line saying why there is nothing to load."""
    root = env.game_dir / ROOT
    if not root.is_dir():
        logger.info("no scripts: %s does not exist", root)
        return None
    if not (root / ENTRY).is_file():
        logger.info("no scripts: %s has no %s, which is the pack's entry", root, ENTRY)
        return None
    return root


def _import_pack(root: Path) -> Any:
    """Import the pack inside its own unit context and answer that context, without enabling it.

    The caller enables it, because a reload has to have the new incarnation's registrations staged before the old
    one's are released; doing both here would leave the order to whoever called.
    """
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(PACKAGE, root / ENTRY, submodule_search_locations=[str(root)])
    if spec is None or spec.loader is None:
        msg = f"importlib could not build a specification for {root}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    with active(IDENTITY) as pack:
        try:
            spec.loader.exec_module(module)
        except BaseException:
            _ = sys.modules.pop(PACKAGE, None)
            raise
    return pack


def _purge() -> int:
    """Drop every module of the pack, so the import that follows reads the files as they are now."""
    names = [name for name in sys.modules if name == PACKAGE or name.startswith(PACKAGE + ".")]
    for name in names:
        del sys.modules[name]
    importlib.invalidate_caches()
    return len(names)


pack: Any = None


def _load_pack() -> None:
    """The first load: import the pack and let what it registered reach the bus."""
    global pack
    root = _pack_root()
    if root is None:
        return
    pack = _import_pack(root)
    pack.enable()
    logger.info("scripts: %s loaded", root)


async def _reload() -> str:
    """Drop the pack and load it again, answering what happened in one line."""
    global pack
    root = _pack_root()
    if root is None:
        return "no scripts to reload"
    if pack is None:
        pack = _import_pack(root)
        pack.enable()
        return "scripts loaded"
    dropped = _purge()
    pack = await loader.replace(pack, lambda: _import_pack(root))
    logger.info("scripts: reloaded from %s", root)
    return f"scripts reloaded ({dropped} modules dropped)"


_load_pack()


@on_server_start
def _server_started(server: object) -> None:
    """Say once per server that the pack is live on it, which is also what proves the marker reaches here."""
    logger.info("scripts: live on %s", server)


@command("scriptive reload")
async def _reload_command(source: Any) -> None:
    """`/scriptive reload`: the pack's own command, on its own path."""
    answer = await _reload()
    source.sendSystemMessage(Component.literal(answer).java)
