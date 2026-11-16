# 10. Lifecycle primitives come from composat, at the effect-scope layer

**Status**: accepted, 2026-11-16.

## Context

ADR 0004 (staged loading), 0006 (revocable registration) and 0009 (a loop on the host thread) put the shape of a
load in place; this record takes the primitives from a library instead of writing them. `composat` — the sibling
project at `../composat`, v1.0.2 — implements that machinery and has written ADRs about it:

- `EffectScope.put(effect) -> Revoke`, LIFO, exactly once, `reopen()` for the next epoch
  (its ADR 0006).
- `load_unit` / `load_units` / `fingerprint_of`, plus `composat.std.pluggable.UnitLoader` for moving a
  loaded module onto a new generation.
- `Assembly` with `load/unload/reload/enable/disable/drain` hooks and the verbs
  `start/stop/migrate/enable/quiesce/admit/evict/replace`.

What it deliberately does *not* do — stated in its README's "What this is not" — is exactly the part
that is specific to this project: no discovery mechanism, no version axis, no file watcher, no event
dispatcher, no configuration system, no runtime of its own.

## Decision

Adopt in three layers, cheapest first, and stop where the cost stops paying:

1. **`EffectScope`** for revocation. It is stdlib-only: loaded by path on the shipped runtime (CPython
   3.13.3), `scope.py` imports nothing from `composat` and behaves as documented — revoke releases only
   the tail after its checkpoint, `dispose` releases last-registered-first, a closed scope refuses more,
   `reopen` answers a new scope while the old one stays closed, and revoke is idempotent.
2. **`Unit` / `fingerprint_of`'s shape** for units and staleness: a hash of the syntax, recorded on the
   module it loaded.
3. **`Assembly` / `Component` / `require()`** — deferred. This project's consumers are unit authors, not
   a multi-tenant deployment; the lifecycle is what is needed, and dependency injection has no
   consumer yet.

It is vendored into the embedded runtime or pinned in the runtime manifest, never an unpinned
`pip install`: the runtime ships `pip` and `jep` and no resolver guarantees.

## Consequences

- One trap is inherited deliberately rather than discovered: `.pyc` staleness is judged by the source's
  mtime and size, and the mtime it records is whole seconds, so two equal-length edits within one
  second serve the **old** bytecode while the fingerprint correctly reports the new source. `composat`
  avoids it by compiling the text it just read (`_SourceOnlyLoader`). Any reload implementation here
  must do the same, whether or not `composat` is present.
- Two identity concepts now need a stated relation: `composat`'s component identity is
  `module.qualname` and has no version axis (its ADR), while a unit's identity is a manifest's
  (ADR 0003). The rule is: the unit is the versioned thing; a component inside it is not.
- Revocation is now one mechanism, not two: `reclaimable.put(...)` is the seam, and the kernel's
  `revoke_all(unit)` is a scope disposal. A second stack on the Python side would be the thing to
  refuse in review.
- The dependency has to be pinned and shipped with the runtime, which belongs in the runtime manifest
  that does not exist yet.

## Alternatives considered

- **Re-implement.** Independence, and it re-derives the same traps — the `.pyc` second-resolution
  staleness, reopen-answers-a-new-scope rather than clearing, revocation idempotency — each of which
  costs an incident to learn.
- **Adopt everything, including `Assembly`.** Commits to dependency injection before any consumer asks
  for it, and drags a state machine and its report vocabulary into a project whose users are writing a
  script.
- **Wait for `composat` to be older than 1.0.2.** The coupling is affordable precisely because both
  sides can be changed by the same person; waiting buys nothing that reading its ADRs does not.
- **A third-party dependency-injection framework.** None of them is a lifecycle; the lifecycle is the
  part that is hard.
