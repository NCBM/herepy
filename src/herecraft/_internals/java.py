"""herecraft._internals.java — asking a JEP proxy what Java class it is, in one place.

jep 4.3 turned every type into a heap type, and 4.4's ``PyJClass`` stopped proxying
``java.lang.Class``'s methods, so ``obj.getClass().getName()`` — the way this project used to ask —
now raises ``AttributeError: 'jep.PyJClass' object has no attribute 'getName'``.

Every ``PyJObject`` answers ``java_name`` instead: jep computes it with
``java.lang.Class.getName()`` on the object's own runtime class, which is the same answer with one
call instead of two. The version that lacks the attribute keeps working through the old route.

Nothing here reaches into a wrapper or a registry; this module only answers questions about classes.
"""

from __future__ import annotations

from typing import Any


def java_class_name(jobj: Any) -> str:
    """The Java class name of a JEP proxy, e.g. ``net.minecraft.core.BlockPos``."""
    try:
        return str(jobj.java_name)
    except AttributeError:  # pragma: no cover - jep before 4.3 answered through java.lang.Class
        return str(jobj.getClass().getName())


def java_superclasses(jobj: Any) -> list[str]:
    """The Java superclasses of ``jobj``, nearest first, without its own class.

    Walks ``java.lang.reflect`` rather than the proxy, because a proxy carries only its own class.
    This crosses into Java for each step, so it is for the rare case where the exact class is not
    the one asked for — not for the common path.
    """
    from .javans import ReflectWrapper

    names: list[str] = []
    reflected = ReflectWrapper.forClass(jobj.getClass()).getSuperclass()
    while reflected is not None:
        names.append(str(reflected.getName()))
        reflected = reflected.getSuperclass()
    return names
