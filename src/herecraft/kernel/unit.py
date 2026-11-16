"""A unit's own book of registrations, and the scope that takes them back.

Loading a unit is what creates its context: the loader wraps the import in :func:`active`, and every
`register*` call made while that is in progress lands here. A registration made outside a load has no
owner, so it is refused rather than filed under a guess.

The context holds an `EffectScope` from composat (ADR 0010). Each registration puts one *release*
effect in it, so the scope is a stack of things to undo, and revoking releases the effects from a
checkpoint on — last-registered first, exactly once.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
import logging

from herecraft._vendor.composat.scope import EffectScope, Revoke

logger = logging.getLogger("herecraft.kernel")

# The units whose load is in progress on this thread, innermost last. A plain list rather than a
# context variable because loading happens on the one thread that owns the interpreter, and the
# caller of a registration is that thread by construction.
_LOADING: list[UnitContext] = []


@dataclass(eq=False)
class UnitContext:
    """What one unit registered, held as effects the scope releases together."""

    name: str
    _scope: EffectScope = field(default_factory=EffectScope, repr=False)
    _staged: list[Callable[[], None]] = field(default_factory=list, repr=False)
    _hooks: dict[str, list[Callable[[], object]]] = field(default_factory=dict, repr=False)
    _enabled: bool = field(default=False, repr=False, init=False)

    def reclaim(self, release: Callable[[], object]) -> Revoke:
        """Put ``release`` in this unit's scope; the answer releases this and everything after it.

        The answer is a checkpoint, not a single effect: registering A then B and releasing A
        releases B too, because a unit's registrations come back in the reverse of the order they
        went in. A unit that wants one registration gone registers its effects so that a checkpoint
        falls where it wants the stack cut.

        It is a coroutine because releasing may await (ADR 0010), and the host thread runs those on
        its loop (ADR 0009): a caller that needs the completed state awaits the answer instead of
        expecting the release to have happened when the call returns.
        """
        if self._scope.closed:
            msg = f"unit {self.name!r} is being torn down, so it takes no more registrations"
            raise RuntimeError(msg)
        return self._scope.put(release)

    def stage(self, hand_over: Callable[[], None]) -> None:
        """Keep ``hand_over`` until this unit is enabled: that is when a registration reaches the bus.

        Loading is a stage of its own (ADR 0004): nothing a unit does while it loads touches the
        game, so a unit that raises leaves no listener behind and a listener is up only for handlers
        whose unit finished loading.
        """
        self._staged.append(hand_over)

    def add_hook(self, marker: str, fn: Callable[[], object]) -> None:
        """Keep ``fn`` as work this unit asked for under ``marker``, in the order it asked (ADR 0018).

        A hook runs once, when the loader calls it, and leaves nothing for a scope to release. It carries the one
        thing a bus cannot express: code that belongs to a distribution rather than to an event.
        """
        self._hooks.setdefault(marker, []).append(fn)

    def hooks(self, marker: str) -> tuple[Callable[[], object], ...]:
        """The work this unit asked for under ``marker``, in the order it asked."""
        return tuple(self._hooks.get(marker, ()))

    def enable(self) -> None:
        """Let this unit's registrations reach the bus, in the order the unit made them.

        A unit that revoked everything while it loaded has nothing left to hand over: its scope is
        closed, and the effects that would have gone to the bus went with it.
        """
        if self._scope.closed:
            logger.debug("Unit %r revoked its registrations before it was enabled", self.name)
            return
        for hand_over in self._staged:
            hand_over()
        self._staged.clear()
        self._enabled = True

    @property
    def enabled(self) -> bool:
        """Whether this unit's registrations have reached the bus."""
        return self._enabled

    async def revoke_all(self) -> None:
        """Release everything this unit still holds, last-registered first, and take no more.

        A release that raises does not keep the rest from running — the scope goes on and gathers
        them — but it is reported here instead of thrown: a unit coming down has no caller to answer
        to, and a teardown that stops at its first failure leaves the later effects held forever.
        """
        try:
            await self._scope.dispose()
        except ExceptionGroup as failures:
            for failure in failures.exceptions:
                logger.error("Releasing a registration of unit %r failed", self.name, exc_info=failure)
        logger.debug("Revoked %r", self.name)

    @property
    def registrations(self) -> tuple[str, ...]:
        """The names of the effects this unit still holds, oldest first."""
        return self._scope.effects()


@contextmanager
def active(name: str) -> Iterator[UnitContext]:
    """Make ``name`` the unit that the registrations made in this block belong to."""
    unit = UnitContext(name)
    _LOADING.append(unit)
    try:
        yield unit
    finally:
        _LOADING.pop()


def current() -> UnitContext:
    """The unit loading right now; refuse the call if there is none.

    A registration with no unit behind it would be a handler nobody can name and nobody can take
    back, so it is an error rather than an anonymous entry in a global map.
    """
    if not _LOADING:
        msg = (
            "registration outside a unit load: it would belong to nobody and could never be revoked. "
            "Register from a unit's module-level code, which is where a load puts the context."
        )
        raise RuntimeError(msg)
    return _LOADING[-1]
