# 6. Every registration is revocable, and the handle belongs to the kernel

**Status**: accepted, 2026-11-16.

## Context

Registration today has no owner and no way back:

- `herecraft.event` keeps `_HANDLER_REGISTRY: dict[str, list[tuple[Callable, bool]]]` — a global map
  of handlers, with no field saying which unit registered one and no removal path.
- `EventBridge` attaches listeners as anonymous lambdas: `bus.addListener(eventType, event -> ...)`.
  Nothing keeps the lambda, so nothing can pass it to `IEventBus.unregister`.
- `_bootstrap` runs once and `registerPythonListeners` runs once (ADR 0004), so "remove this unit" has
  never had to be expressible.

Reload (0018), disabling a unit, and "one broken unit is that unit's problem" all need removal.
Once the surface grows past events — commands, block and item registration, tick callbacks — a
per-registration owner is much cheaper to have than to add.

## Decision

Every registration goes through a context that belongs to the kernel:

- the context is created per unit and carries the unit's identity;
- every `register*` call takes the unit's identity from the context, never from a keyword the caller
  passes, so attribution cannot be forgotten;
- every `register*` call returns a **revoke** callable, and the context answers `revoke_all()`;
- the Java side keeps the listener object it added, so it can remove exactly that one;
- the Python side implements this on `composat`'s `EffectScope` (ADR 0010) rather than growing a
  parallel stack: `revoke_all()` is the scope's disposal, LIFO and exactly once.

## Consequences

- `/herepy reload` becomes expressible: `revoke_all(unit)` → stages 2–4 of ADR 0004.
- Errors are attributable: "this handler raised" names the unit that registered it, which today is
  impossible because the map has no owner.
- One layer of indirection on every registration path, paid once per registration, not per call.
- A registration made *during* a revocation has to be handled deliberately: it lands in the scope being
  torn down, so `EffectScope` refuses it once closed — the teardown has to be complete before a unit
  can register again.
- The kernel now has a concept (`revoke`) that every future registration API has to honour; a new API
  that returns nothing is a hole rather than a convenience.

## Carried out, 2026-11-16

The context is `herecraft/kernel/unit.py`: `active(name)` marks the unit a load belongs to, `current()`
answers it, and a registration made with no load in progress is refused rather than filed under a
guess. `UnitContext.reclaim(release)` puts one release effect in the context's scope and returns the
checkpoint that releases it; `revoke_all()` disposes the scope. `herecraft/kernel/bridge.py` is the
only way a registration reaches Java, and `herecraft.event` is its only caller: `@event` takes the
unit from `current()`, records an `_Handler` carrying that name, stages the request that Java retain
the event class, and puts a release effect in the scope — named after the handler, and doing what
`_drop` does: take the entry off the dispatch table and Java's listener with it if it was the last.

Registration is staged rather than immediate, which is ADR 0004's stages 3 and 4: `stage` collects
per unit what it asked for, and nothing touches a bus until the loader calls `enable()` once every
unit has loaded. So a unit that raises leaves no listener behind, a unit that revoked everything while
it loaded is enabled into nothing, and a listener is up only for handlers whose unit finished loading.
The loader (`herepy-shims.py`) wraps each import in `active(name)`, keeps what loaded, and enables
them at the end.

Java keeps the object it gave the bus: `EventBridge` holds one `Trigger` per event class, keyed by the
Java class name, and `IEventBus.unregister` takes that same object back. `retain` counts units rather
than registrations, so a listener goes up for the first unit listening to a class and comes down with
the last one; a handler that needs to run synchronously replaces an asynchronous listener for its class
(the union can only grow that way). `registerPythonListeners` and `get_registered_types` are gone —
a unit hands over what it staged when it is enabled, so there is no snapshot to take.

`composat`'s `scope.py` is copied into `herecraft/_vendor/composat/` byte for byte, with the release,
commit and SHA-256 in `_vendor/README.md`. Installing it was not an option: it is built with
`pdm-backend` and would need an index to reach, and this project adopts one layer of it, not the
package. `ruff` excludes the directory, since the copy is not this project's to reformat.

Three things the scope's shape decided, none of them obvious from the ADR:

- **A revoke is a checkpoint, not a single handle.** `put` answers a callable that releases everything
  from that point on, so releasing a unit's first registration releases the ones after it. That is
  what a LIFO stack means and `reclaim`'s docstring says so; the record's "every `register*` returns a
  revoke callable" is satisfied with that meaning, not with per-effect removal.
- **A revocation is awaited.** The scope's operations are coroutines (ADR 0010), and the host thread
  runs them on its loop (ADR 0009 has since landed), so `revoke_all` is `async` and the caller that
  needs the completed state awaits it: `herepy-shims.py` awaits it while loading a unit that raised.
  There is no longer a synchronous path to a finished revocation, which is the shape the record
  predicted — the seam that would have had to change is the one that is now `await unit.revoke_all()`.
- **The count Java keeps is per event class, not per unit**, so one unit revoking its handler leaves
  the listener up for the units still listening. Nobody's registration is removed but the one asked
  for.

Verified at runtime with two temporary units. One registers on `ServerStartedEvent` and
`ServerStartingEvent` and then revokes while it is still loading; the other registers on the same two
events and revokes from inside its `ServerStartingEvent` handler, after it was enabled. `smoke` is the
third, listening to `ServerStartingEvent` as it always did:

```
[herecraft.revoke_check] held before revoking: ('on_server_started', 'on_server_starting')
[herecraft.revoke_check] held after revoking: ()
Python listener for ...ServerStartingEvent is up (async)     <- at enable, after every unit loaded
Python listener for ...ServerStartedEvent is up (async)
[herecraft.revoke_later] revoke_later: server starting, revoking this unit
Python listener for ...ServerStartedEvent is down            <- last listener for its class
[herecraft.revoke_later] held after revoking: ()
[herecraft.smoke] smoke: server starting, motd='Dev - 新的世界'
```

The unit that revoked while loading never reached a bus at all. The one that revoked from a handler
took its own class's listener down, left `ServerStartingEvent` up because `smoke` still listens to it,
and `smoke`'s handler ran in the same dispatch it was revoked in. Neither revoked handler ran. Both
units were removed after the run; `smoke` remains as the standing proof.

Also fixed on the way, because the alternative was a silently dead interpreter: an exception escaping
a `PythonRunner` task ended the thread that runs every later task, and losing that thread loses the
whole Python side with nothing in the log to say why. The queue now reports a failing task and keeps
running, and dispatch wraps its own call for the same reason.

## Alternatives considered

- **Restart the interpreter on reload.** JEP's `SharedInterpreter` attaches a thread to shared state;
  there is no cheap restart, and it would take every other unit down with it.
- **Owner tag only, no handles.** Enough to *report* who registered what, and not enough to take a
  lambda off the bus — the NeoForge API wants the object it was given.
- **`IEventBus.unregister(dummyListenerObject)` with one dummy per unit.** Works for NeoForge, couples
  the kernel to one bus's API, and says nothing about registrations that are not on a bus (commands,
  registry entries, tick callbacks).
- **Let each unit revoke itself in a teardown hook.** Puts the burden on unit authors, and the one unit
  that forgets leaks a listener forever, invisibly.
