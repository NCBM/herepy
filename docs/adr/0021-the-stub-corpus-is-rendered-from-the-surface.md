# 21. The stub corpus is rendered from the surface, and a patch is an overlay

**Status**: proposed, 2026-11-17.

## Context

The stub corpus was built by reflecting Java classes and appending `ast.unparse` output to `<package>/__init__.pyi`.
Three properties of that arrangement decided this record:

- A run appended to whatever the output tree already held, so a second run left a second copy of every class.
- Nothing checked what was written. NeoForge adds members named `neoforge$setValidBlocks`; the `$` reached the `def`
  line and the module stopped being Python.
- The class set comes from a jar's entry list, so the corpus is the size of the classpath. The surface is smaller: the
  names `herecraft/api` declares, and what those classes reach. A declared name the entry list does not carry goes
  unnoticed.

## Decision

The corpus is generated, and what it contains is decided by the surface:

- **The class set is the closure of what the surface declares.** The seeds are the names in `herecraft/api` — the
  `__java_class_name__` values and the classes the bootstrap hands over. The closure adds superclasses, interfaces,
  and the types of parameters, return values and fields, transitively. A jar's entry list enumerates what a
  classpath holds; it never decides what is generated.
- **A module is rendered from every class it holds and written whole.** A run replaces what an earlier run wrote and
  removes modules whose classes have left the set, so the output tree holds what the last run decided and nothing
  else. Two runs over the same surface produce the same bytes.
- **A module is checked before it is written.** It is parsed, and every declared name — class, member, parameter — is
  checked to be a Python identifier. A class that would leave its module unparseable is left out and named in the
  report.
- **A member no Python expression can spell is left out of its class and named in the report.** `neoforge$getX` is
  reachable through `getattr` and cannot be declared in a stub; the class around it stays whole.
- **A run writes `stubgen-report.json`.** Per class: `written`, `rejected` or `failed`, the module it went to, the
  reason, and the members left out. The report is an output of the run as much as the stubs are.
- **A generated stub is never edited; a correction is an overlay.** An overlay is a file named after its Java class
  holding the members a generated class is missing or has wrong; the renderer merges it over the generated class,
  applies overlays in a fixed order, and lists the ones it applied. An overlay whose class is no longer in the
  closure is reported as stale, so a correction that stopped being needed is visible.
- **What the class file does not carry comes from a data overlay.** Parameter names are the first case: the bytecode
  of the JDK and of NeoForge carries no `MethodParameters`, so reflection answers `arg0`, and Parchment's data holds
  the names. Docstrings are the second: a class file carries no javadoc, so a class or method's text comes from the
  same data, with its markup turned into the text a stub shows. The overlay is keyed by class, method and JVM
  descriptor, which survives a recompilation. Where no data covers a member, `argN` is written and the report counts
  it.
- **The toolchain's inputs are this repository's to build.** The name data and the stub corpus are derivatives of
  the development toolchain, produced here from the versions in `gradle.properties`. The generator reads them from
  the build tree; a path inside a tool's private cache is not an input.
- **The generator is a unit that runs on demand.** It takes its seed classes and its output directory as arguments and
  runs in a process that already has the classpath — a command, or a script pack entry. The mod's boot generates
  nothing (ADR 0004), and a mod that wants stubs for its own classes runs the same unit against its own jar.

## Consequences

- The corpus is the size of the surface, so `herecraft-stubs` (ADR 0013) is a package worth publishing, and a reader
  sees the classes a unit can reach and nothing else.
- Idempotency is a property of the writer, which makes CI's comparison of generated output against committed output a
  real check (ADR 0012).
- The overlay is a second place where part of the surface is written down. It has to stay small: a correction that
  survives three regenerations is a rule missing from the generator, and the report is where that shows.
- The renderer takes a class model, so `tools/checks/check.py` holds it without a JVM. The closure walk needs a
  classpath and stays outside.
- A member that reflection sees and Python cannot spell is a blind spot with a name: `getattr` is the only way in, and
  the report lists each one.
- A docstring appears where the data carries one. A class the game's own code never documented keeps none, and the
  report counts the docstrings a run applied.
- Generation needs the classpath a mod runs with, so the offline gate cannot run it. What the gate holds is the
  renderer, on models the check file builds.
- Two machines that agree on `gradle.properties` produce the same corpus, and a corpus can be rebuilt from a
  checkout.

## Alternatives considered

- **Keep writing per class into an existing file.** Cheaper per class, and every run is a diff of the whole tree in
  disguise: the writer has to know what is already there, and nothing checks that the two halves agree.
- **Read the name data where the tool cached it.** A path under a tool's cache belongs to one machine and one
  resolution, so a corpus built from it cannot be rebuilt from the checkout.
- **Generate every class the classpath holds.** It needs no closure walk, and it describes classes no unit reaches.
- **Patch generated stubs by hand, and commit the result.** The next regeneration loses every patch, and nothing says
  which of the hand edits were corrections.
- **Regenerate into a scratch tree and diff.** It gives the same bytes as replacing in place and leaves two trees to
  keep in step; the prune rule already makes the output tree a pure function of the input.
- **Take names from `genSources` output.** NeoGradle can decompile with Parchment applied, and it costs a decompiler
  and a Java parser in the toolchain, both of which then have to be trusted for every signature. Parchment's own data
  is the names without either.
- **One stub set per consuming mod.** Each mod would carry a corpus and the surface would be re-decided per mod; the
  unit form of the generator covers the need with one copy.
