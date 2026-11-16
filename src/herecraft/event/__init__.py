"""herecraft.event — Python event handler registration and dispatch for NeoForge events."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import inspect
import logging
from typing import Any, overload

from herecraft import env
from herecraft._internals.java import java_class_name
from herecraft.api._registry import wrap
from herecraft.api.events._base import Side
from herecraft.kernel import bridge, current, host

logger = logging.getLogger("herecraft.event")


@dataclass(eq=False, slots=True)
class _Handler:
    """One registration: the unit that owns it, what it calls, and where it runs."""

    unit: str
    fn: Callable[..., Any]
    sync: bool


# Maps Java canonical class name → the handlers listening to it. An entry leaves when the last
# handler for its class is revoked, and Java's listener leaves with it.
_HANDLER_REGISTRY: dict[str, list[_Handler]] = {}

# Maps Python annotation type → Java canonical class name (for decorator resolution)
_TYPE_NAME_CACHE: dict[type, str] = {}


@overload
def event(fn: Callable[..., Any], /) -> Callable[..., Any]: ...
@overload
def event(*, sync: bool = False) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


def event(fn: Callable[..., Any] | None = None, /, *, sync: bool = False) -> Any:
    """Register a Python function as a NeoForge event handler.

    The handler runs on the host loop, and may be a coroutine: the dispatch awaits it either way
    (ADR 0009). ``sync`` is for handlers whose decision the game thread waits on — a cancellable
    handler — and it is their cost that the dispatch deadline bounds.

    Usage::

        @event
        async def on_server_start(e: ServerStartingEvent):
            await something()

        @event(sync=True)
        def on_block_break(e: BlockBreakEvent):
            e.cancel()  # requires sync=True
    """

    def _register(func: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        if not params:
            msg = f"@event handler {func.__qualname__} must have at least one parameter (the event)"
            raise TypeError(msg)

        annotation = params[0].annotation
        if annotation is inspect.Parameter.empty:
            msg = f"@event handler {func.__qualname__}: first parameter must have a type annotation"
            raise TypeError(msg)

        # `from __future__ import annotations` makes every annotation a string, and the module that
        # wrote the name is the only place it means anything. The function keeps a reference to its
        # own globals, so the decorator does not have to guess at a stack frame — which it did, and
        # got the decorator's own module for `@event(sync=True)`.
        if isinstance(annotation, str):
            annotation = eval(annotation, func.__globals__)

        # Get the Java class name from the annotation
        event_class_name = _resolve_java_class_name(annotation)
        # A client class that this distribution does not have would be a failure at the first dispatch, long
        # after the unit asked for it and reading like a typo; refuse it here instead (ADR 0017).
        _refuse_if_absent_here(annotation, event_class_name, func)

        _register_handler(event_class_name, func, sync=sync)
        return func

    if fn is not None:
        # @event without parentheses
        return _register(fn)
    # @event(sync=True) with parentheses
    return _register


def listen(event_class: Any, fn: Callable[..., Any], *, sync: bool = False) -> Callable[..., Any]:
    """Register ``fn`` as a handler for an event class named by a wrapper, without the annotation dance.

    The markers in `herecraft.markers` come here: they know their event class already, and what they need is
    exactly what an `@event` handler gets — the unit's ownership, the staged hand-over to the bus, and a release
    that goes with the unit (ADRs 0004, 0006).
    """
    event_class_name = _resolve_java_class_name(event_class)
    _refuse_if_absent_here(event_class, event_class_name, fn)
    _register_handler(event_class_name, fn, sync=sync)
    return fn


def _register_handler(event_class_name: str, fn: Callable[..., Any], *, sync: bool) -> None:
    """Put one handler on the dispatch table for an event class this module has already resolved."""
    # The unit that asked is the unit loading right now: a handler has no keyword saying whose it
    # is, so the context is the only place the answer can come from (ADR 0006).
    unit = current()
    handler = _Handler(unit.name, fn, sync)
    _HANDLER_REGISTRY.setdefault(event_class_name, []).append(handler)
    # Nothing reaches the bus while the unit is loading; this runs when the unit is enabled.
    unit.stage(lambda: bridge.retain(event_class_name, sync=sync))

    def release_handler() -> None:
        """Take this registration off the dispatch table, and Java's listener with it if it was last."""
        _drop(event_class_name, handler)
        if unit.enabled:
            bridge.release(event_class_name)

    release_handler.__name__ = fn.__qualname__
    unit.reclaim(release_handler)
    logger.debug(
        "Registered %s handler for %s in unit %r (sync=%s)",
        fn.__qualname__,
        event_class_name,
        unit.name,
        sync,
    )


def detach(unit_name: str) -> int:
    """Take every handler of one unit off the dispatch table, leaving the bus alone.

    The new incarnation loads before the old one's bindings are released (ADR 0018), which keeps the listener for
    an event class on the bus across two incarnations. The old scope's release runs afterwards, finds the entries
    gone, and `_drop` tolerates that.
    """
    removed = 0
    for event_class_name, handlers in list(_HANDLER_REGISTRY.items()):
        kept = [handler for handler in handlers if handler.unit != unit_name]
        removed += len(handlers) - len(kept)
        if kept:
            _HANDLER_REGISTRY[event_class_name] = kept
        else:
            del _HANDLER_REGISTRY[event_class_name]
    return removed


def _drop(event_class_name: str, handler: _Handler) -> None:
    """Take one registration off the dispatch table; the bus is the caller's business."""
    handlers = _HANDLER_REGISTRY.get(event_class_name)
    if handlers is None:
        return
    try:
        handlers.remove(handler)
    except ValueError:
        return
    if not handlers:
        del _HANDLER_REGISTRY[event_class_name]
    logger.debug("Released %s handler for %s in unit %r", handler.fn.__qualname__, event_class_name, handler.unit)


def _resolve_java_class_name(annotation: Any) -> str:
    """Resolve a type annotation to a Java canonical class name."""
    cached = _TYPE_NAME_CACHE.get(annotation)
    if cached is not None:
        return cached

    # Check __java_class_name__ first — all Event subclasses carry it
    java_name: str | None = getattr(annotation, "__java_class_name__", None)
    if java_name:
        _TYPE_NAME_CACHE[annotation] = java_name
        return java_name

    # JavaWrapper subclass — reverse-lookup in wrapper registry
    from herecraft.api._base import JavaWrapper

    if isinstance(annotation, type) and issubclass(annotation, JavaWrapper):
        from herecraft.api._registry import get_wrapper_registry

        for reg_name, wrapper_cls in get_wrapper_registry().items():
            if wrapper_cls is annotation:
                _TYPE_NAME_CACHE[annotation] = reg_name
                return reg_name

    # Java class used directly as an annotation — ask it what Java class it is
    try:
        name = java_class_name(annotation)
    except (AttributeError, TypeError):
        pass
    else:
        _TYPE_NAME_CACHE[annotation] = name
        return name

    msg = f"Cannot resolve Java class name from annotation: {annotation!r}"
    raise TypeError(msg)


def _refuse_if_absent_here(annotation: Any, event_class_name: str, func: Callable[..., Any]) -> None:
    """Refuse a client-only event where no client exists (ADR 0017).

    The alternative is a `ClassNotFoundException` from Java on the first dispatch attempt: later, and reading
    like a misspelled class name rather than like a handler in the wrong place.
    """
    if getattr(annotation, "__side__", Side.BOTH) is not Side.CLIENT:
        return
    dist = env.current()
    if dist is not env.Dist.DEDICATED_SERVER:
        return
    msg = (
        f"@event handler {func.__qualname__} listens to {event_class_name}, which exists only where there is a "
        f"client, and this is {dist.describe()}: nothing here could ever dispatch it."
    )
    raise RuntimeError(msg)


def _get_event_handlers(java_event: Any) -> tuple[str, list[_Handler], Any] | None:
    """Return (class_name, handlers, wrapped_event), or None when nothing is registered."""
    class_name = java_class_name(java_event)
    handlers = _HANDLER_REGISTRY.get(class_name)
    if not handlers:
        return None
    return class_name, handlers, wrap(java_event)


@host.entry("event.dispatch")
async def dispatch(java_event: Any) -> None:
    """Run an event's async handlers, on the loop. Called from Java by that name (ADR 0009).

    A handler may be a coroutine, so it is awaited: the crossing is a coroutine, and the work under it
    gets the same cancellation and failure reporting as the crossing itself.
    """
    result = _get_event_handlers(java_event)
    if result is None:
        return
    class_name, handlers, wrapped = result
    # A handler may revoke a registration while this runs, so the list is read once.
    for handler in tuple(handlers):
        if handler.sync:
            continue
        try:
            answer = handler.fn(wrapped)
            if inspect.isawaitable(answer):
                await answer
        except Exception:
            logger.exception("Error in handler %s of unit %r for %s", handler.fn.__qualname__, handler.unit, class_name)


@host.entry("event.dispatch_sync")
async def dispatch_sync(java_event: Any) -> bool:
    """Run an event's sync handlers and answer whether it asked to be cancelled.

    Java waits for this answer under a deadline, so what it costs is a game-thread stall: a handler
    that needs longer than that belongs in an async one, where nobody waits for it.
    """
    result = _get_event_handlers(java_event)
    if result is None:
        return False
    class_name, handlers, wrapped = result
    cancel = False
    from herecraft.api.events._base import Event

    # A handler may revoke a registration while this runs, so the list is read once.
    for handler in tuple(handlers):
        if not handler.sync:
            continue
        try:
            answer = handler.fn(wrapped)
            if inspect.isawaitable(answer):
                answer = await answer
            if answer is False:
                cancel = True
        except Exception:
            logger.exception(
                "Error in sync handler %s of unit %r for %s", handler.fn.__qualname__, handler.unit, class_name
            )
        if not cancel and isinstance(wrapped, Event):
            cancel = wrapped.is_canceled

    return cancel
