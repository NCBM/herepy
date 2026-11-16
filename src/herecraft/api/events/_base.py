from __future__ import annotations

from enum import Enum
from typing import Any, ClassVar

from herecraft.api._base import JavaWrapper

_cancelable_cache: dict[type, bool] = {}


class Side(Enum):
    """Whether an event class exists on a distribution that has no client (ADR 0017).

    Presence, not where it fires: `BlockBreakEvent` is `BOTH` because the class is on a dedicated server's
    classpath, even though nothing dispatches it on a client. A wrapper that does not say is a wrapper that lies
    about what a server can dispatch.
    """

    BOTH = "both"
    CLIENT = "client"


class Event(JavaWrapper[Any]):
    """Base for all NeoForge event wrappers."""

    __java_class_name__: ClassVar[str] = ""

    #: Which distributions have this class. Every concrete wrapper states it, and `__init_subclass__` refuses one
    #: that names a Java class and leaves this out.
    __side__: ClassVar[Side]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Refuse a wrapper that names a Java class but not which distributions have it."""
        super().__init_subclass__(**kwargs)
        if "__java_class_name__" in cls.__dict__ and "__side__" not in cls.__dict__:
            msg = (
                f"{cls.__name__} names a Java class but declares no __side__, so nothing can tell whether a "
                "dedicated server could ever dispatch it (ADR 0017)"
            )
            raise TypeError(msg)

    @property
    def is_cancelable(self) -> bool:
        """Cached per class — cancelability is a static property of the event type."""
        cls = type(self)
        result = _cancelable_cache.get(cls)
        if result is None:
            result = hasattr(self._jobj, "setCanceled")
            _cancelable_cache[cls] = result
        return result

    @property
    def is_canceled(self) -> bool:
        if not self.is_cancelable:
            return False
        return bool(self._jobj.isCanceled())

    def cancel(self) -> None:
        """Cancel this event. Only works if the event implements ICancellableEvent."""
        self._jobj.setCanceled(True)
