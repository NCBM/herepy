# 13. The repository is split by published artifact

**Status**: proposed, 2026-11-16.

## Context

The tree holds one Gradle project, with the Python package at `src/herecraft/` beside `src/main/java`, and a CPython
distribution with its generated typing tree under `runs/client/`. `src/herecraft/` reaches the run directory through a
symlink at `runs/client/python/lib/python3.13/herecraft/` — one copy of the code, no drift, and an arrangement
nothing in the build creates or checks (a symlink does not survive packaging either).

The Java half and the Python half are one protocol apart (ADR 0002) and are released together, which
is the coupling that decides the question.

## Decision

One repository, split by what gets published:

```
packages/herecraft/     the Python API package: own pyproject, own tests, no Minecraft to run them
packages/herecraft-stubs/   generated stubs, PEP 561, published
mod/                    the NeoForge mod (Gradle), the kernel and its primitives
api-spec/               the single source the generated artifacts come from (ADR 0012)
runtime/                a manifest: which CPython, which jep, per platform, with hashes
examples/               example units, which double as end-to-end fixtures
docs/adr/               these records
```

- `herecraft` becomes importable and testable **without Minecraft**, against a fake host (ADR 0002).
- The run directory gets its Python package from the build rather than from a symlink into the source
  tree; a CI check fails on drift.
- Binaries are not committed: `runtime/` holds versions and hashes, not a 3 MB interpreter.
- Generated stubs are not committed into the run directory; they are a build artifact.
- CI is path-filtered: a change under `packages/` runs Python checks only, a change under `mod/` or
  `api-spec/` runs Gradle too.

## Consequences

- The project cannot be tested today at all outside the game; this is the change that fixes it, and it
  is the precondition for ADR 0002 and ADR 0012 being verifiable at all.
- The MDK-shaped root (`src/main/java`, `src/main/resources`, `build.gradle` at the top) moves, which is
  a large diff with no behaviour change.
- Release is two artifacts from one commit, with one version source.
- A path-filtered CI is a thing to maintain correctly: a filter that misses a dependency turns a
  failure into a green build.

## Alternatives considered

- **Two repositories.** Defensible if the release cadence ever forks (mod rarely, `herecraft` often). It
  is not the case now: the protocol changes ripple across both halves in the same commit, and two
  repositories would need cross-repo compatibility tests to recover what one commit gives for free.
- **Keep the template's layout**, adding `docs/` and `tests/` beside it. Cheapest now, and it leaves
  `src/herecraft/` being both a Python package and a sibling of `src/main/java`, which is what makes
  "the package is copied into the runtime" look reasonable.
- **Vendor everything into one Gradle project** (the Python package as a resource). Removes the copy
  problem by removing the package's identity: no `pyproject.toml`, no typing artifact, no package that
  can be imported and tested outside the jar.
