"""herecraft.kernel.boot — what Java calls once: load the units, enable them, serve the loop (ADR 0018).

Loading happens while the mod is constructed, which is where the game's own orchestration calls it and the only
place where the loop can own its thread. The phases are these three and nothing else: discovery in
`herecraft.kernel.loader`, loading and enabling here, and the loop from `herecraft.kernel.host`.

The load runs inside the loop, and Java waits on it: a server that starts mid-load hands its lifecycle event to
nobody, and that event is the one such a handler exists for.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from herecraft import __api__, env
from herecraft.kernel import loader
from herecraft.kernel.host import serve

logger = logging.getLogger("herecraft.kernel")


class Ready(Protocol):
    """What Java offers so the mod can wait until the units are loaded (ADR 0018)."""

    def markReady(self) -> None:
        """Note that every unit has been loaded and enabled."""
        ...


def start(ready: Ready | None = None) -> None:
    """Load every unit under the game directory's `mods`, enable them, and serve the loop until shutdown.

    Java calls this on the host thread as the last thing the bootstrap does, and the call ends when the loop does:
    the loop's life is the thread's. ``ready`` hears when the units are in place, because the caller waits on that
    before the game moves on.
    """
    dist = env.current()
    game_dir = env.game_dir
    logger.info("herecraft %s on %s in %s", __api__, dist.describe(), game_dir)
    serve(lambda: _boot(game_dir, ready))


async def _boot(game_dir: Path, ready: Ready | None) -> None:
    """The loop's first task: discovery, then loading, then the enabled set, then out of the way."""
    try:
        _load(game_dir)
    finally:
        # Even a failed load has to release the caller that is waiting on it: a report of "not ready" while the
        # game is already running would be worse than a slow start.
        if ready is not None:
            ready.markReady()


def _load(game_dir: Path) -> None:
    """Discovery, loading and enabling, one unit's failure at a time."""
    mods_dir = game_dir / "mods"
    sources = loader.discover(mods_dir)
    if not sources:
        logger.info("no units: %s holds no .pyz and no unit directory", mods_dir)
        return

    loaded: list[loader.Loaded] = []
    for source in sources:
        try:
            loaded.append(loader.load(source))
        except Exception:
            logger.exception("unit %s did not load, so it contributed nothing", source.manifest.id)

    for entry in loaded:
        try:
            loader.enable(entry)
        except Exception:
            logger.exception("unit %s failed while its registrations were handed over", entry.source.manifest.id)

    logger.info("%d of %d units loaded", len(loaded), len(sources))
