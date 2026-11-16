"""herecraft.commands — a command is a registration like any other (ADR 0018).

A unit names a literal path and a function; Java keeps the list and puts it on the dispatcher every time the game
builds one, since a dispatcher lasts one server. The work runs on the loop like everything else, so the game thread
hands it over and moves on, and the unit words its own answer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import inspect
import logging
from typing import Any, Protocol

from herecraft.kernel import current, host

logger = logging.getLogger("herecraft.kernel")


class Dispatcher(Protocol):
    """What Java's `CommandBridge` offers: which literal paths exist, and who may run them."""

    def declare(self, path: str, permission: int) -> None:
        """One more command: a literal path and the permission level it needs."""
        ...

    def withdraw(self, path: str) -> None:
        """One command gone, because the unit that registered it was revoked."""
        ...


@dataclass(frozen=True, slots=True)
class _Command:
    """One registration: where it answers, who may run it, what it does, and whose it is."""

    path: str
    permission: int
    run: Callable[[Any], Any]
    unit: str


_dispatcher: Dispatcher | None = None
_commands: dict[str, _Command] = {}


def install_commands(dispatcher: Dispatcher) -> None:
    """Attach the Java side; HerePy does this before any unit is loaded."""
    global _dispatcher
    _dispatcher = dispatcher
    logger.debug("Java command bridge attached: %r", dispatcher)


def command(path: str, *, permission: int = 2) -> Callable[[Callable[[Any], Any]], Callable[[Any], Any]]:
    """Register the decorated function as the command at ``path``, a literal path such as ``"scriptive reload"``.

    The function is handed the game's command source, and may answer it in its own words. Whatever it registered
    goes when its unit goes, like any other registration (ADR 0006).
    """

    def decorate(fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
        register(path, fn, permission=permission)
        return fn

    return decorate


def register(path: str, fn: Callable[[Any], Any], *, permission: int = 2) -> None:
    """Register ``fn`` at ``path``: one or more bare literals separated by spaces."""
    if _dispatcher is None:
        msg = "no Java command bridge is attached, so a command has nowhere to go. HerePy attaches one first."
        raise RuntimeError(msg)
    unit = current()
    normalized = " ".join(path.split())
    parts = normalized.split(" ")
    # A literal path is what Java can build without an argument parser, which is the whole of what this offers.
    if not normalized or not all(part.isidentifier() for part in parts):
        msg = f"a command path is one or more bare literals separated by spaces, not {path!r}"
        raise ValueError(msg)
    if normalized in _commands:
        other = _commands[normalized].unit
        msg = f"unit {unit.name!r} cannot claim {normalized!r}: unit {other!r} already did"
        raise RuntimeError(msg)
    _commands[normalized] = _Command(normalized, permission, fn, unit.name)
    _dispatcher.declare(normalized, permission)
    _ = unit.reclaim(lambda: _withdraw(normalized))
    logger.debug("Registered command %r in unit %r (permission %s)", normalized, unit.name, permission)


def _withdraw(path: str) -> None:
    """Take one command off the list, here and in Java; a unit that is going takes its commands with it."""
    if _commands.pop(path, None) is None:
        return
    if _dispatcher is not None:
        _dispatcher.withdraw(path)


@host.entry("commands.run")
async def _run(path: str, source: Any) -> None:
    """Run one command on the loop, with the source Java handed over."""
    entry = _commands.get(path)
    if entry is None:
        logger.debug("command %r was asked for, and is no longer registered", path)
        return
    try:
        answer = entry.run(source)
        if inspect.isawaitable(answer):
            _ = await answer
    except Exception:
        logger.exception("command %r in unit %r raised", path, entry.unit)
