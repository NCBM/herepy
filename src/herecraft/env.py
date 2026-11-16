"""herecraft.env — the facts Java hands Python once, before any unit is loaded.

The distribution is a closed set (ADR 0017): a value the mod does not know is refused when it arrives, rather
than every later check quietly taking the "server" branch. It is a Python enum rather than the Java `Dist`
proxy, so it has a type an editor can read and no stub has to describe an injected global.

What runs is the loader's decision, taken by the markers a unit holds (ADR 0018). A unit reads this value to word a
message, and the one branch the kernel takes on it refuses a client-only event where no client exists.
"""

from __future__ import annotations

from enum import Enum
import logging
from pathlib import Path

logger = logging.getLogger("herecraft.kernel")


class Dist(Enum):
    """Which distribution this process is: the question `dist` answers, and nothing else."""

    CLIENT = "client"
    DEDICATED_SERVER = "dedicated_server"

    @property
    def has_client(self) -> bool:
        """Whether this distribution ships a client at all — not whether this code runs on one."""
        return self is Dist.CLIENT

    def describe(self) -> str:
        """How a message names it: "a client" or "a dedicated server"."""
        return "a client" if self is Dist.CLIENT else "a dedicated server"


dist: Dist
"""The distribution this process is, set by :func:`install` before any unit is discovered or loaded."""

game_dir: Path
"""The game directory, set by :func:`install`: where `mods/` and the runtime tree are, from this mod's side."""

_installed: Dist | None = None


def install(name: str, directory: str) -> Dist:
    """Take the distribution and the game directory from Java, once, and refuse anything the mod does not know.

    Called from the bootstrap on the host thread before discovery: after that, a failure is about what a unit
    did rather than about which distribution it is running on.
    """
    global _installed
    try:
        value = Dist(name.strip().lower())
    except ValueError:
        known = ", ".join(member.name for member in Dist)
        msg = f"{name!r} is not a distribution this mod knows; the ones it knows are {known}"
        raise ValueError(msg) from None
    if _installed is not None and _installed is not value:
        msg = (
            f"the distribution is already {_installed.name}, and one process cannot become {value.name}: the "
            "value is fixed for the life of the interpreter"
        )
        raise RuntimeError(msg)
    _installed = value
    globals()["dist"] = value
    globals()["game_dir"] = Path(directory)
    logger.debug("distribution: %s, game directory: %s", value.name, directory)
    return value


def current() -> Dist:
    """The distribution, refusing a read before :func:`install` instead of answering `None`."""
    if _installed is None:
        msg = (
            "the distribution was read before it was installed. The mod installs it in the bootstrap, before "
            "discovery, so a read this early means the kernel was entered without one."
        )
        raise RuntimeError(msg)
    return _installed
