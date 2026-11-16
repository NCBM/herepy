"""The kernel's half of a listener on a Java event bus.

A registration reaches Java through this module and nowhere else. `retain` asks Java to put one
listener object on a bus and keep it by handle; `release` hands that handle back so the bus can drop
exactly the object it was given (ADR 0006). Java counts the units listening to one event class, so
the listener goes up when the first unit asks and comes down when the last one stops.

Nothing here knows which unit asked: the count is per event class, and the unit's own book of what
it registered is the context's business.
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger("herecraft.kernel")


class Bus(Protocol):
    """What Java's `EventBridge` offers: one counted listener per event class."""

    def retain(self, java_class_name: str, needs_sync: bool) -> None:
        """One more unit listens to this event class; put the listener up if it is the first."""
        ...

    def release(self, java_class_name: str) -> None:
        """One unit stopped listening; take the listener down when it was the last."""
        ...


_bus: Bus | None = None


def install_bridge(bus: Bus) -> None:
    """Attach the Java side; HerePy does this before any unit is loaded."""
    global _bus
    _bus = bus
    logger.debug("Java event bus attached: %r", bus)


def retain(java_class_name: str, *, sync: bool) -> None:
    """Note one registration for this event class, and have Java listen if it does not already."""
    if _bus is None:
        msg = (
            f"no Java event bus is attached, so the handler for {java_class_name} has nowhere to go. "
            "HerePy attaches one before it loads units."
        )
        raise RuntimeError(msg)
    _bus.retain(java_class_name, sync)


def release(java_class_name: str) -> None:
    """Drop one registration for this event class; the last one takes Java's listener with it."""
    if _bus is None:
        return
    _bus.release(java_class_name)
