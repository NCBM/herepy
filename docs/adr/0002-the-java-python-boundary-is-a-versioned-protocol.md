# 2. The Java/Python boundary is a versioned protocol, not a set of imports

**Status**: accepted, 2026-11-16.

## Context

The two halves of this project are joined by string names that neither side checks:

- `HerePy`'s constructor drives Python with `interpreter.exec("from herecraft.api._setup import
  _bootstrap")` and `interpreter.invoke("_bootstrap", ...)`, then `interpreter.runScript(... +
  "/herecraft/herepy-shims.py")`.
- `EventBridge` re-executes `"from herecraft.event import _dispatch"` on **every event dispatch**, then
  calls `interp.invoke("_dispatch", event)`.
- `javans.inject(name, val)` puts Java classes into Python's global scope by bare name; `herecraft`
  reads those names and fails with an `AttributeError` if one is missing.
- `herecraft.event.get_registered_types()` answers `list[tuple[str, bool]]`, and the meaning of those
  two positions exists only in the Java code that unpacks them.

A version mismatch between the mod jar and the `herecraft` package on disk therefore surfaces as an
`AttributeError`, an empty registry, or a silently wrong event class — inside a game tick, with a
traceback that names neither half. Since `src/herecraft/` is copied into the run directory's Python
tree by hand (nothing in `build.gradle` does it), the two halves can and do drift.

## Decision

The boundary is one explicitly versioned protocol.

- Both sides carry a `PROTOCOL` version. It is checked once at bootstrap; on mismatch the mod refuses
  to start and names both versions in the message.
- The Java side injects **one** object — a host façade — instead of one global per Java type. Python
  reaches Java through it, and what it may reach is therefore one place in the code rather than every
  `javans` name.
- Python callables the mod needs are resolved **once** at bootstrap and held as handles, never
  re-imported per call. This removes the per-event `interp.exec`, which is both string-typed and paid
  on every event.
- `herecraft` declares its own version and the protocol range it implements; the mod declares the
  range it requires.
- One version source. The mod version, `herecraft.__version__` and `PROTOCOL` derive from one file, so
  a release cannot ship three numbers that disagree.

## Consequences

- The drift above becomes a startup failure with a readable message instead of a runtime
  `AttributeError`.
- The host façade is the seam a test double plugs into, which is what makes the Python half testable
  without launching Minecraft (until now the only way to test `herecraft` was `runClient` and reading
  logs).
- Every call that used to go through `javans.<Name>` now goes through the façade: a small amount of
  indirection, and one place to change when the host changes.
- The two halves still ship separately, so the protocol version is a real compatibility axis and needs
  its own bump discipline — it is not the mod version.

## Alternatives considered

- **Keep injecting raw classes per Java type.** It works today, and every new type is a new injection
  with no place to put a compatibility check; the failure mode stays "missing attribute at runtime".
- **Let Python import Java classes itself** through JEP's import hook (`from net.minecraft.core import
  BlockPos`), dropping the injection protocol. Tempting, and `herecraft` already relies on that hook
  for `java.lang`/`org.slf4j`; but then the contract *is* JEP's import hook, and the mod has no way to
  state or check which `herecraft` it is talking to.
- **A generated `.pyi` as the contract.** Types without a runtime check: it catches a wrong signature
  in the editor and nothing at all about a version mismatch.
- **Detect mismatches lazily, per call.** Same information, discovered at the worst moment, repeatedly.
