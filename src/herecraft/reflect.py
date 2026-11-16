from __future__ import annotations

from typing import TYPE_CHECKING, cast, overload

from java.lang import Object
from java.lang.reflect import Type

from ._internals.javans import ReflectWrapper


@overload
def as_reflectable(
    cls: type[Object] | Object,
) -> ReflectWrapper.ReflectClass: ...


@overload
def as_reflectable(
    cls: type[Type] | Type,
) -> ReflectWrapper.ReflectType: ...


def as_reflectable(
    cls: type[Object | Type] | Object | Type,
) -> ReflectWrapper.ReflectClass | ReflectWrapper.ReflectType:
    """Convert a Java Class or Type to a ReflectWrapper object."""
    try:
        return ReflectWrapper.forClass(cast("type[Object]", cls))
    except TypeError:
        if TYPE_CHECKING:
            assert isinstance(cls, Type)
        return ReflectWrapper.forType(cls)
