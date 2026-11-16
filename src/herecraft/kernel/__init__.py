"""herecraft.kernel — who a registration belongs to, how it is taken back, and where it runs.

A registration is not the kernel's: it belongs to the unit that made it, and the unit's context is
where that ownership is kept. The context is the only thing that knows which unit a handler came
from, and it is the only way to release what the unit registered — a handler has no keyword saying
whose it is, so attribution cannot be forgotten (ADR 0006).

What a context holds is composat's `EffectScope` (ADR 0010): revocation is a scope disposal, LIFO and
exactly once, rather than a stack of this project's own.

`host` is the thread all of it runs on: one loop, owned by the host thread, with `submit` and
`call_sync` as the only ways in (ADR 0009).
"""

from herecraft.kernel import host
from herecraft.kernel.bridge import install_bridge
from herecraft.kernel.unit import UnitContext, active, current

__all__ = ["UnitContext", "active", "current", "host", "install_bridge"]
