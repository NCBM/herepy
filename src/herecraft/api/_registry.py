from __future__ import annotations

from typing import Any

from herecraft._internals.java import java_class_name, java_superclasses

# Java canonical class name -> Python wrapper class
_WRAPPER_REGISTRY: dict[str, type] = {}

# Java canonical class name -> JEP-proxied Java class object (for constructors)
_JAVA_CLASS_REGISTRY: dict[str, Any] = {}


def get_wrapper_registry() -> dict[str, type]:
    """Return the wrapper registry for read-only external access."""
    return _WRAPPER_REGISTRY


def register_wrapper(java_class_name: str, wrapper_cls: type) -> None:
    """Register a Python wrapper class for a Java class name."""
    _WRAPPER_REGISTRY[java_class_name] = wrapper_cls


def register_java_class(java_class_name: str, jclass: Any) -> None:
    """Store the JEP-proxied Java class object for use by factory methods."""
    _JAVA_CLASS_REGISTRY[java_class_name] = jclass


def wrap(jobj: Any) -> Any:
    """Auto-wrap a JEP Java proxy in its registered Python wrapper.

    Falls through to the raw proxy if no wrapper is registered.
    Walks superclasses so e.g. ServerPlayer -> Player, and only when the exact class misses: the
    walk crosses into Java per step, and the exact class is the usual answer.
    """
    if jobj is None:
        return None
    try:
        wrapper_cls = _WRAPPER_REGISTRY.get(java_class_name(jobj))
    except Exception:
        return jobj
    if wrapper_cls is not None:
        return wrapper_cls(jobj)

    try:
        for name in java_superclasses(jobj):
            wrapper_cls = _WRAPPER_REGISTRY.get(name)
            if wrapper_cls is not None:
                return wrapper_cls(jobj)
    except Exception:
        return jobj
    return jobj


def get_java_class(name: str) -> Any:
    """Retrieve a previously injected Java class object."""
    cls = _JAVA_CLASS_REGISTRY.get(name)
    if cls is None:
        msg = f"Java class {name!r} not injected. Ensure HerePy registered it at startup."
        raise KeyError(msg)
    return cls
