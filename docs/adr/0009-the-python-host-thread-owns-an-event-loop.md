# 9. The Python host thread owns an asyncio event loop

**Status**: accepted, 2026-11-16.

## Context

`PythonRunner` is a thread plus a `BlockingQueue<Consumer<Interpreter>>`: the queue thread takes one
task at a time and runs it to completion. Everything the Python half does is therefore synchronous, and
one long task blocks every other. `EventBridge`'s sync path goes further and blocks the **game thread**
on that queue (`executeSyncBlocking(...).get()`) to learn whether a cancellable event should be
cancelled.

The lifecycle primitives that ADR 0010 adopts are `async` throughout: `await assembly.start(key)`,
`await scope.dispose()`, `await wait.serving(...)`. Without a loop in the host thread, none of them can
be used, and a decision would have to be re-implemented synchronously.

## Decision

The Python host thread creates and owns exactly one asyncio event loop, and every crossing is a
coroutine:

- **Java → Python, fire and forget**: submit the coroutine to the loop, return a future, do not wait.
- **Java → Python, synchronous** (cancellable events): submit, then wait on the future with a
  **deadline**. On timeout the work is cancelled and the outcome degrades to "not cancelled", logged
  with the unit and event named. The game thread is never waited on indefinitely.
- **Re-entrancy is refused, not tolerated**: a coroutine running on the loop may not reach back for a
  synchronous dispatch. The seam checks the current thread and raises instead of deadlocking, which is
  what the alternative produces.
- The loop is the only place Python runs, so the existing "single-threaded interpreter" invariant is
  unchanged — it is now "single loop".

Measured on the shipped runtime (CPython 3.13.3), with a loop on its own thread and callers on others:

| Property | Result |
|---|---|
| `submit` answers | pass |
| synchronous call answers within its deadline | pass |
| deadline refuses instead of blocking (0.05 s requested) | pass, 0.050 s elapsed |
| timed-out work is cancelled rather than left running | pass |
| re-entrancy refused instead of deadlocking | pass, `RuntimeError` |
| submission order preserved over 200 submits | pass |
| 64 concurrent synchronous callers | pass |
| loop thread stops on close | pass |

## Consequences

- ADR 0010's primitives are usable as written.
- A synchronous dispatch now has a policy that must be written once and honoured everywhere: deadline,
  degradation, logging. Two different timeouts in two places is a bug waiting.
- The loop only advances while the host thread is inside it, so work that must happen "soon" needs a
  task, not a thread — a timer or a poll has to be an `EffectScope.after`, not a `Timer`.
- Debugging gets a new failure mode: a coroutine that never awaits blocks the loop, which looks exactly
  like "Python is slow". Worth a watchdog later; not worth one now.
- `Consumer<Interpreter>` disappears from the Java API in favour of submitting coroutines, which is a
  visible change to every call site that has one.

## Alternatives considered

- **Keep the thread and queue, no loop.** Preserves the code as written, and gives up ADR 0010 — the
  staging, revocation and reload machinery would have to be re-implemented synchronously, which is
  where the second implementation of a decided thing starts.
- **Drive the loop from Minecraft's tick** with a slice of `run_until_complete` per tick. There is no
  loop in Minecraft to borrow, slicing gives *worse* latency guarantees than a dedicated thread, and
  the deadline for a cancellable event would be quantised to tick length (50 ms) — the difference
  between a decision and a coin flip.
- **One loop per unit**, giving isolation at the cost of the single-interpreter invariant and of JEP's
  thread affinity.
- **`run_until_complete` everywhere, never `run_coroutine_threadsafe`.** Equivalent for the sync path
- **`run_until_complete` everywhere, never `run_coroutine_threadsafe`.** Equivalent for the sync path
  and unable to express "submit now, answer later", which is what async event dispatch is.

## Carried out, 2026-11-16

`herecraft/kernel/host.py` is the seam. It creates the loop on the host thread, runs the unit loader as
its first task (`serve`), and offers three entries: `submit`, `call_sync`, and `stop`. Entries are
registered by name at import — `event.dispatch` and `event.dispatch_sync` in `herecraft/event` — so Java
names a protocol entry rather than an attribute of wherever the caller happened to be, and an unknown
name is refused with the list of names that exist.

`PythonRunner` is now the thread plus that loop: `start(init)` runs `init` on the thread that owns the
interpreter, and `init` ends by running `herepy-shims.py`, whose last line is `serve(load_units)`. The
call does not return, so the thread's life is the loop's life. The loader is a coroutine because loading
a unit awaits now — `await unit.revoke_all()` — which is ADR 0010's shape arriving on schedule;
`UnitContext.reclaim` answers composat's `Revoke` instead of a hand-rolled checkpoint, and `_settle` and
its `_PENDING` set are gone.

**jep decides what a crossing can be.** An `Interpreter` belongs to the thread that created it: any
other thread gets `Invalid thread access`, and `Jep.attach` is the way onto one. `attach(true)` shares
the interpreter's `__main__`; `attach(false)` shares its state but not its globals, so it cannot resolve
the seam at all — a detour that reads like "the module is gone". A view is made per calling thread and
kept, because a thread that crosses once crosses again.

So the handover happens on the caller's thread and nothing else does: `submit` schedules the coroutine
with `asyncio.run_coroutine_threadsafe` and returns; `call_sync` schedules it and waits in
`Future.result(SYNC_TIMEOUT)`, a `threading.Condition` wait that releases the GIL, which is why the loop
keeps running while the game thread waits. "The loop is the only place Python runs" holds for everything
a unit wrote; the one line that hands work over cannot hold for it, because the loop is what it hands to.

Three things the measurements decided, none of them obvious from the record above:

- **The deadline bounds the wait, not the work.** `SYNC_TIMEOUT = 0.1 s`, written once in the seam, which
  also cancels and logs. Cancellation reaches a coroutine at its next await, so an `async def` handler is
  really stopped and a plain `def` handler is not: it runs to the end holding the loop, and every
  dispatch queued behind it pays the deadline too. Seen in the client — a 0.3 s `def` sync handler timed
  out, and an entity-join event dispatched inside those 0.3 s timed out as well.
- **A timed-out dispatch answers "none", and the caller reads that as "not cancelled".** The event
  proceeds uncancelled; the seam logs once, naming the entry and the wait. That is the whole degradation
  policy, and `EventBridge` holds none of it.
- **`attach` is per thread and per interpreter, so a view is a resource.** It is made once per thread and
  never closed, which is deliberate: closing a view would ask the shared interpreter to wind down. The
  cost is one small object per thread that ever crossed, and there are a handful of those.

`EventBridge` no longer re-executes an import per dispatch: the async half is one `submit`, the sync half
is one `call_sync`, and a failure to hand over is logged rather than thrown into the bus, where it used
to take the server down with it. Handler failures are reported by the loop with the unit and entry
named, so `logPythonFailure` and its traceback fetch are gone. `herecraft/_internals/typedefs.py` and
`javans.py` mirror the new Java surface (`start`, `submit`, `callSync`, `close`).

One defect surfaced on the way: `@event(sync=True)` could not resolve its annotation at all under
`from __future__ import annotations`. The decorator guessed at a stack frame and, from the decorator
form, got its own module; it now resolves in the handler's own globals, which is the only frame in which
the name can mean anything.

Verified at runtime with two temporary units, both deleted afterwards; `smoke` is the third, listening
to `ServerStartingEvent` as it always did. One registered an async handler, a 0.3 s sync handler, a
re-entrant call, and a sync handler that answers both ways on `EntityJoinLevelEvent`; the other revoked
itself from an async handler and registered a handler that then had to stay silent.

```
[herecraft-python/DEBUG] Python host thread is up
[herecraft.shims] Loading unit: loop_check
[herecraft.loop_check] async handler: thread=Dummy-1 on-loop=True
[herecraft.loop_check] async handler: resumed after await
[herecraft.loop_check] slow sync handler: 0.3 s on Dummy-1
[herecraft.kernel] event.dispatch_sync did not answer within 0.10 s: it was cancelled and the answer counts as none
[herecraft.loop_check] re-entrant synchronous call refused: event.dispatch_sync asked for a synchronous
    answer from the thread that has to give it, so the wait would never end. A coroutine that needs to
    cross hands the work over with submit.
[herecraft.loop_revoke] revoking this unit from an async handler
[herecraft.loop_revoke] revoked; holds=() enabled=True
[herecraft.loop_check] sync handler lets net.minecraft.server.level.ServerPlayer join
[EventBridge/DEBUG] Python handler canceled event net.neoforged.neoforge.event.entity.EntityJoinLevelEvent
[herecraft.smoke] smoke: server starting, motd='Dev - 新的世界'
```

The thread Python reports is `Dummy-1`: jep makes the Python thread state without registering a
`threading.Thread`, so every log line from Python names a thread nobody can find. Worth knowing before
reading one of these logs and concluding the loop is somewhere else.

Where the loop shows through:

- **A handler that blocks without awaiting holds the loop**, and the deadline logs the symptom, which is the way to
  find one.
- **A slow unit delays `enable()` for every unit.** Loading runs inside the loop now, and a unit that
  spends 24 s writing stubs — the stub generator does — pushes every listener up after the world has
  already started, so no handler sees the server-start events. That is ADR 0004's staging measured
  rather than argued.
- **The seam resolves a target per crossing** (`_host.submit`), which is ADR 0002's business: one place
  that lists the entries and one version that both halves agree on. Not this record's.
