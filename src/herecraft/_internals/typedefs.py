from collections.abc import Callable, Iterator
from typing import Any, Final, Protocol, Self, TypeVar, runtime_checkable

_T = TypeVar("_T")
_T_co = TypeVar("_T_co", covariant=True)
_T_contra = TypeVar("_T_contra", contravariant=True)
_KT = TypeVar("_KT")
_VT = TypeVar("_VT")


# ── JEP runtime-provided protocols ───────────────────────────────────────────
# JEP adds these dunder methods to PyJObjects that implement the corresponding
# Java interfaces (see jep wiki: Accessing-Java-Objects-in-Python).
# Using Protocol (not ABC) so that type checkers do not require stubs to
# re-declare every abstract method — structural subtyping is enough.


@runtime_checkable
class JAutoCloseable(Protocol):
    """java.lang.AutoCloseable / java.io.Closeable — JEP adds __enter__/__exit__."""

    def __enter__(self) -> Self: ...
    def __exit__(self, *args: object) -> None: ...
    def close(self) -> None: ...


@runtime_checkable
class JIterable(Protocol[_T_co]):
    """java.lang.Iterable — JEP adds __iter__."""

    def __iter__(self) -> Iterator[_T_co]: ...


@runtime_checkable
class JIterator(Protocol[_T_co]):
    """java.lang.Iterator — JEP adds __next__ and __iter__."""

    def __next__(self) -> _T_co: ...
    def __iter__(self) -> "JIterator[_T_co]": ...


@runtime_checkable
class JCollection(JIterable[_T_co], Protocol[_T_co]):
    """java.util.Collection — JEP adds __len__ and __contains__."""

    def __len__(self) -> int: ...
    def __contains__(self, item: object) -> bool: ...


@runtime_checkable
class JList(Protocol[_T]):
    """java.util.List — JEP adds __getitem__ and __setitem__."""

    def __iter__(self) -> Iterator[_T]: ...
    def __len__(self) -> int: ...
    def __contains__(self, item: object) -> bool: ...
    def __getitem__(self, index: int) -> _T: ...
    def __setitem__(self, index: int, value: _T) -> None: ...


@runtime_checkable
class JSet(JCollection[_T_co], Protocol[_T_co]):
    """java.util.Set."""


@runtime_checkable
class JMap(Protocol[_KT, _VT]):
    """java.util.Map — JEP adds __getitem__, __setitem__, keys(), items()."""

    def __getitem__(self, key: _KT) -> _VT: ...
    def __setitem__(self, key: _KT, value: _VT) -> None: ...
    def keys(self) -> Any: ...
    def items(self) -> Any: ...


@runtime_checkable
class JComparable(Protocol[_T_contra]):
    """java.lang.Comparable."""

    def compareTo(self, other: _T_contra) -> int: ...


@runtime_checkable
class JRunnable(Protocol):
    """java.lang.Runnable."""

    def run(self) -> None: ...


# ── HerePy internals ─────────────────────────────────────────────────────────


class JepInterpreter(Protocol):
    def invoke(
        self,
        callee: str,
        arg1_kwds_args: Any | dict[str, Any] | list[Any] = None,
        arg2_unused_kwds: Any | dict[str, Any] = None,
        /,
        *args: Any,
    ) -> Any: ...

    def eval(self, code: str) -> bool: ...

    def exec(self, code: str) -> None: ...

    def runScript(self, filename: str) -> None: ...

    def getValue(self, code: str) -> Any: ...

    def set(self, name: str, val: Any) -> None: ...

    def close(self) -> None: ...


class JPythonRunner(Protocol):
    """The Python host thread (ADR 0009): the loop it serves, and the two ways into it."""

    def __init__(self) -> None: ...

    def start(self, init: Callable[[JepInterpreter], None]) -> None: ...

    def submit(self, target: str, *args: object) -> None: ...

    def callSync(self, target: str, *args: object) -> object | None: ...

    def close(self) -> None: ...


class SLFLogger(Protocol):
    ROOT_LOGGER_NAME: Final = "ROOT"

    def getName(self) -> str: ...

    def trace(self, arg0: str, /) -> None: ...

    def debug(self, arg0: str, /) -> None: ...

    def info(self, arg0: str, /) -> None: ...

    def warn(self, arg0: str, /) -> None: ...

    def error(self, arg0: str, /) -> None: ...
