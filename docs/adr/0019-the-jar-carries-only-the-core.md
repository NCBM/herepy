# 19. The jar carries only the core, and the script track is always a second file

**Status**: proposed, 2026-11-16.

## Context

A release needs a place to publish to, a tag to attach a file to, and a channel whose file-type list allows a second
file of an unfamiliar extension. The shape below is what the files take once those exist.

The script track is its own HerePy mod, released as a `.pyz` that discovery finds in `mods/` (0018). Delivery differs
by channel: a GitHub release carries whatever is attached to it, and a mod platform accepts what its file-type list
allows, which for a second file of an unfamiliar extension is nothing to plan around.

Embedding the pack in the jar would make one download enough everywhere. The jar and the script track change on
different clocks, and anything inside the jar becomes part of the jar's identity — its version, its hash, its
build. A jar carrying a fast-moving unit cannot be re-published without also changing the unit, and the unit cannot
move without a jar release. Those two clocks are the point of the script track being a separate mod.

## Decision

- **The jar carries the core.** A release embeds no copy of the script track, on any channel. Installing the jar
  gives a mod that starts, loads whatever units sit in `mods/`, and holds the script track once it arrives as a
  unit.
- **The script track is one file: `HerePyScriptiveSupport.pyz`** — a packaged unit with its own version and its own
  `api` range, dropped into `mods/` beside the jar. It is attached to every GitHub release and stays off the mod
  platform.
- **A platform-only install is a supported state.** The core starts, logs what it is, and registers the commands its
  units asked for, of which there are none. Nothing has a message to print for a feature that was never installed.
- **A platform user fetches one file from the release page** to get the script track, and the install instructions
  say so.
- **The dev loop uses the release shape.** The build drops the unit into each run directory's `mods/`, so discovery,
  the `api` check and loading run exactly as a release runs them; the difference is which build produced the file.

## Consequences

- The platform audience gets the core alone. That is a product decision with a documentation bill: the mod
  description has to say where the rest of it is.
- The two clocks stay two: the script track updates, downgrades or previews without touching the jar, and the jar
  re-publishes without dragging the script track's version along.
- The `api` range keeps a newer `.pyz` off an older jar, and the message names both files so a user knows which one
  to replace.
- An install holds one copy of the script track, so no precedence rule is needed anywhere.
- The dev loop sits one build step away from the release shape, which is what keeps the two honest.

## Alternatives considered

- **Embedding the pack in the jar.** One download on every channel, at the price of a jar whose identity depends on
  a unit that changes faster than it — plus a fixed internal prefix that becomes protocol, a precedence rule for
  the newer `.pyz` someone drops beside it, and a measurement of whether a path inside a jar can be a `__path__`.
- **Two files as the only shape.** GitHub can carry them and the platform cannot, so a platform install would be
  broken rather than core-only.
- **No script track at all.** 0008 settled that one.
- **Shipping the support unit inside the runtime tree**, where the dev loop keeps it beside the user's scripts. The
  runtime is a pinned artifact with a hash (0014, 0015), so a fast-moving unit inside it couples two release
  cadences and changes what the manifest pins.
