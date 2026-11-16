from __future__ import annotations

from typing import override

from java.lang import Object


class JavaWrapper[T: Object]:
    """Base for Pythonic wrappers over JEP-proxied Java objects."""

    __slots__: tuple[str, ...] = ("_jobj",)

    _jobj: T

    def __init__(self, jobj: T) -> None:
        self._jobj = jobj

    @property
    def java(self) -> T:
        """Escape hatch: the raw JEP-proxied Java object."""
        return self._jobj

    @override
    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._jobj!r})"

    @override
    def __eq__(self, other: object) -> bool:
        if isinstance(other, JavaWrapper):
            return bool(self._jobj.equals(other._jobj))
        return NotImplemented

    @override
    def __hash__(self) -> int:
        return int(self._jobj.hashCode())
