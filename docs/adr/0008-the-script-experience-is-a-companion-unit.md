# 8. The script experience is a first-party companion unit, not kernel logic

**Status**: accepted, 2026-11-16.

## Context

Given ADRs 0004 and 0006, what remains of the KubeJS-like track is policy and presentation: which
directories are scanned, which stage a file belongs to, what `/reload` does, how an error is presented,
whether files are ordered by name. None of it needs kernel access — all of it needs the primitives
already decided.

There is also an audience question. The `scripts/` track is aimed at modpack authors (drop a file, edit
it, reload); the packaged track is aimed at unit authors (versioned, distributed, installed).
The first audience's entire value proposition is "install one thing, drop one file".

## Decision

- The kernel ships **primitives only**: staged loading (0004), revocable registration (0006), one source over
  `mods/` (0018), identity and manifests (0003).
- The script experience is a **companion unit** written against the public API, living in this
  repository, and shipped as its own file beside the kernel (0019) so a user can install it with one
  more drop.
- It is a packaged unit itself, with a manifest, loaded through the same path as any other.

## Consequences

- The companion dogfoods the packaged-unit API: if the kernel's API is insufficient for our own script
  track, the companion breaks first and the gap is found by us.
- Version skew becomes a three-way matrix (kernel / `herecraft` / companion), which is what the `api`
  range in ADR 0003 exists for. The failure message must say "upgrade the companion", not just "api
  mismatch".
- The companion loads the pack itself, so the order "the script track runs before the scripts it loads" comes from
  who loads whom rather than from `dependencies` (0018).
- A broken script takes its pack down: one pack is one unit, so the kernel's unit-level boundary is the boundary
  (0018).
- The kernel keeps its distance from the `scripts/` layout: the path and the reload live in the companion, and the
  kernel sees a unit.

## Alternatives considered

- **Kernel ships the script track.** Fewer moving parts and one fewer version to keep in step, at the
  cost of the kernel becoming an application, and of the packaged-unit API never being exercised by
  anyone who can change it.
- **An outside third-party unit.** No dogfood, and no control over the one thing that matters
  operationally: it must run first.
- **No script track at all.** Refuses the audience the `scripts/` directory was designed for.
- **Ship the companion always-on and non-removable.** Simpler to explain, and it makes "the kernel and
  the script track are separate" untestable.

## Open question

Whether the script track is the product's *first* touch. If it is, this decision is wrong — a first touch belongs in
the one download a user makes — and the answer is "the kernel ships it, and 0004/0006 stay because reload needs them
anyway". 0019 makes the cost concrete: the script track is a second file, fetched separately on every channel that
refuses it. Recorded here rather than resolved: it is a product call, and the primitives are the same either way.
