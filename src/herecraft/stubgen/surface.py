"""herecraft.stubgen.surface — the class set a run renders: what the declared surface reaches.

The corpus is not the classpath's size (ADR 0021). It holds what `herecraft/api` declares, and what those
classes reach: a stub names its superclass, its interfaces, the types of its fields, parameters and returns,
and the bounds of its type parameters, so every one of those names has to be in the corpus for the import to
resolve. This module walks that graph and answers the renderer with the classes to render.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from logging import getLogger
from typing import Any

from .core import BASIC_TYPE_MAPPING, STDLIB_TYPE_MAPPING, is_stubgable, reflection

logger = getLogger("herecraft.stubgen.surface")


@dataclass(frozen=True)
class Reach:
    """What one walk decided: the classes to render, and the names it could not follow."""

    classes: tuple[str, ...]
    missing: dict[str, str] = field(default_factory=dict)


def declared_seeds() -> list[str]:
    """The Java names `herecraft/api` declares: what the bootstrap hands over, and every event wrapper.

    The bootstrap's names are in the wrapper registry by the time a unit runs; an event wrapper's name is the
    attribute its class declares, so those are read from the classes themselves.
    """
    from herecraft.api import events
    from herecraft.api._registry import get_wrapper_registry

    names = set(get_wrapper_registry())
    for wrapper in (getattr(events, name) for name in events.__all__):
        declared: str = getattr(wrapper, "__java_class_name__", "")
        if declared:
            names.add(declared)
    return sorted(names)


def closure(seeds: Iterable[str], *, wrapper: type[Any] | None = None, classloader: Any = None) -> Reach:
    """The class a stub needs for every name the seeds reach, transitively.

    `wrapper` and `classloader` are what the walk reflects through; both default to the game's. A name that
    cannot be loaded is recorded and skipped, so one absent class does not stop the walk.
    """
    reflector, loader = reflection(wrapper, classloader)
    render: set[str] = set()
    missing: dict[str, str] = {}
    walked: set[str] = set()
    pending: deque[str] = deque()

    for seed in seeds:
        target = _rendered(seed)
        if target is None:
            missing[seed] = "a name no module can hold"
        else:
            render.add(target)
            pending.append(target)

    while pending:
        name = pending.popleft()
        if name in walked:
            continue
        walked.add(name)
        try:
            rcls = reflector.forClass(loader.loadClass(name))
        except Exception as error:
            logger.warning("Failed to reflect %s: %s", name, error)
            missing[name] = f"{type(error).__name__}: {error}"
            render.discard(name)
            continue
        # A nested class is rendered inside its outer class, so its members are walked as part of this one
        for inner in rcls.getInnerClasses():
            pending.append(str(inner.getName()))
        for referenced in _referenced(rcls):
            target = _rendered(referenced)
            if target is not None:
                render.add(target)
                pending.append(target)

    return Reach(classes=tuple(sorted(render)), missing=missing)


def _rendered(binary_name: str) -> str | None:
    """The class a run renders for a name a type carries, or None when no stub is needed.

    A binary name is what the class file holds (`Outer$Inner`), and the outermost class is what a stub
    declares: the renderer emits a nested class inside the class it belongs to.
    """
    outer, nested, _ = binary_name.partition("$")
    if not is_stubgable(outer):
        return None
    if not nested and (outer in BASIC_TYPE_MAPPING or outer in STDLIB_TYPE_MAPPING):
        # Mapped to a Python type, so the corpus carries no class for it — unless a nested class names it,
        # and then the outer class is what makes `Outer.Inner` resolvable.
        return None
    return outer


def _referenced(rcls: Any) -> Iterator[str]:
    """Every class name a stub of this class names: bases, members, and the bounds of its type parameters."""
    yield from _names_of(rcls.getGenericSuperclass())
    for iface in rcls.getGenericInterfaces():
        yield from _names_of(iface)
    for parameter in rcls.getTypeParameters():
        for bound in parameter.getBounds():
            yield from _names_of(bound)
    for found in rcls.getFields():
        yield from _names_of(found.getGenericType())
    for method in rcls.getMethods():
        yield from _names_of(method.getReturnType())
        for argument in method.getParameters():
            yield from _names_of(argument.getType())
        for parameter in method.getTypeParameters():
            for bound in parameter.getBounds():
                yield from _names_of(bound)
    for constructor in rcls.getConstructors():
        for argument in constructor.getParameters():
            yield from _names_of(argument.getType())
        for parameter in constructor.getTypeParameters():
            for bound in parameter.getBounds():
                yield from _names_of(bound)


def _names_of(rtype: Any) -> Iterator[str]:
    """The classes a type names, following arrays, type arguments, wildcards and bounds."""
    if rtype is None or rtype.isPrimitive() or rtype.isVoid():
        return
    if rtype.isArray():
        yield from _names_of(rtype.getComponentType())
        return
    if rtype.isTypeVariable():
        for bound in rtype.getUpperBounds():
            yield from _names_of(bound)
        return
    if rtype.isWildcard():
        for bound in (*rtype.getUpperBounds(), *rtype.getLowerBounds()):
            yield from _names_of(bound)
        return
    if rtype.isParameterized():
        yield from _names_of(rtype.getRawType())
        for argument in rtype.getActualTypeArguments():
            yield from _names_of(argument)
        return
    yield rtype.getTypeName()
