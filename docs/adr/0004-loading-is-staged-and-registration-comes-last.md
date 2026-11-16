# 4. Loading is staged, and registration comes last

**Status**: accepted, 2026-11-16.

## Context

`HerePy`'s constructor does everything in one pass inside a single `pythonRunner.execute(...)`:

```java
interpreter.runScript(... + "/herecraft/herepy-shims.py");   // units execute here
eventBridge = new EventBridge(pythonRunner, modEventBus);
eventBridge.registerPythonListeners(interpreter);            // bus attached here, once
```

So the set of listeners on the NeoForge bus is a function of "what finished importing during that one
callback". A unit that is loaded later — after a reload, after a mod list change, after a retry — can
never register a handler, because nothing ever runs `registerPythonListeners` again. A unit that throws
halfway through leaves the registry and therefore the bus in a state that depends on where it threw.

## Decision

Loading has stages, and the event bus is touched in the last one only:

1. **discover** — the one source yields candidate units (0018). No user code runs.
2. **load** — each unit is imported (ADR 0003/0018). No game state is touched.
3. **register** — every registration a unit made during `load` is collected, attributed to that unit,
   and NeoForge listeners are attached for the types in it.
4. **enable** — the unit becomes visible to the game.

Only stage 4 touches the bus. A reload is `revoke_all(unit)` followed by stages 2–4, and today the script track is
its one caller (0018).

## Consequences

- A reload is expressible with the same verbs as a first load.
- A unit that fails in `load` contributes nothing to the bus, instead of whatever it got through.
- Errors move earlier: a failed unit fails while the game is still starting, with the unit's name in
  the message, instead of at the first event it should have handled.
- One more thing to get right: a unit enabled in stage 4 may be asked for an event before a later
  unit has finished loading, so "which units are up" has to be answerable during the sequence.

## Alternatives considered

- **One pass, registering as units load** — what exists now, and the reason a unit loaded second can
  never be seen by the bus.
- **Register lazily, on the first event of each type.** Defers the failure to the worst possible
  moment, and cannot express "this unit is not enabled yet".
- **Re-run the whole bootstrap on reload.** Re-creating the interpreter is not available cheaply
  (JEP's `SharedInterpreter` attaches a thread to shared state, it does not restart), and it would take
  every other unit down with it.
