# 12. The Python surface is generated from a spec

**Status**: proposed, 2026-11-16.

## Context

`herecraft/api/` is hand-written: every Minecraft type it exposes is a Python class with a property per
member (`Level.dimension`, `Player.velocity`, `ItemStack.*`), each one a transcription of a Java
signature. In parallel, `herecraft/stubgen/` (730 lines) walks Java classes through `ReflectWrapper` and
emits `.pyi` stubs — the same knowledge, derived from the other direction, in a second place. The
repository has already produced ~450 stub files under `runs/client/python/typings/`.

Two sources of truth for one contract, and the hand-written half covers a few percent of the surface
the stubs describe. They cannot stay in step, and nothing detects the drift.

## Decision

The exposed surface is declared once, as data, and generated:

- a spec (a manifest of Java class → the members exposed, with their Python names and return types);
- from it: the Python wrapper classes, the `.pyi` stubs, the Java-side registry of what was injected,
  and the documentation;
- generation is a build step, and CI compares generated output to committed output, so a spec change
  that was not regenerated fails rather than drifts;
- `stubgen` becomes the generator behind that step instead of a parallel experiment.

## Consequences

- One place to add an exposure, and three artifacts that cannot disagree.
- The spec is reviewable: "what does Python see of `Level`" becomes a diffable list rather than a
  reading of a Python file.
- Anything hand-written that a generator cannot express (a member that needs real logic, like
  `Server.run_command`) needs an explicit escape hatch in the spec, or it becomes a special case in the
  generator — the thing to design carefully, since it is where generated code starts rotting.
- Generated code is not edited by hand; that has to be enforced (a header, a CI check), or the next
  contributor patches the output and the next regeneration loses it.
- The `.pyi` output is a publishable artifact in its own right (a stubs package), which is how stubs
  reach a user's editor without them starting the game.

## Alternatives considered

- **Keep hand-writing wrappers and stubs.** Two truths, no detection, and the stub side is already
  ahead of the hand-written side.
- **Generate the wrappers from reflection at runtime**, with no source artifact. Removes drift and
  removes reviewability, static typing, and IDE completion — the reasons a stub exists.
- **Ship only stubs and use JEP proxies directly.** The Pythonic surface (`player.position` rather than
  `player.position()` over a proxy) is the value of the wrapper layer; giving it up makes the whole
  `api/` package pointless rather than generated.
- **A third-party binding generator** (JPype-style, pybind-style). Nothing available understands a
  Minecraft classpath plus JEP's proxy semantics, and adapting one is more work than generating into
  the shapes already chosen.
