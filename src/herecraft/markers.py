"""herecraft.markers — where a unit says its code belongs (ADRs 0017, 0018).

A marker is a decorator the author imports. It records the function against the unit that is loading — the same
`current()` and context `@event` uses — so a misspelled marker is a `NameError` on the line that made it.

Gating belongs to the library. `on_client` runs after the body of the unit that declared it, on a distribution with
a client. The lifecycle pair registers as an ordinary event handler, so a reload takes it back with everything else
the unit registered.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from herecraft.event import listen
from herecraft.kernel import current

#: The marker `on_client` records under: work for a distribution that has a client (ADR 0018).
CLIENT = "client"


def on_client(func: Callable[[], Any]) -> Callable[[], Any]:
    """Run ``func`` when the unit that declared it has loaded, and only where there is a client."""
    current().add_hook(CLIENT, func)
    return func


def on_server_start(func: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Run ``func(server)`` when a server starts, on every distribution."""
    from herecraft.api.events.server import ServerStartingEvent

    return _lifecycle(ServerStartingEvent, func)


def on_server_stop(func: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Run ``func(server)`` when a server stops, on every distribution."""
    from herecraft.api.events.server import ServerStoppingEvent

    return _lifecycle(ServerStoppingEvent, func)


def _lifecycle(wrapper: type, func: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Register ``func`` as a handler for a lifecycle event, handing it the server rather than the event."""

    def handler(event: Any) -> Any:
        return func(event.server)

    handler.__qualname__ = func.__qualname__
    handler.__doc__ = func.__doc__
    _ = listen(wrapper, handler)
    return func
