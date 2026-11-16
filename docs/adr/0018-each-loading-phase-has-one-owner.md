# 18. Each loading phase has one owner, and a script pack is one unit

**Status**: accepted, 2026-11-17.

## Context

ADR 0004 named four stages of a load — discover, load, register, enable — and nothing owned them: the whole
sequence was `HerePy`'s constructor calling one Python file by path, and that file was a loader living at
`src/herecraft/herepy-shims.py`, a fourth place that is neither the mod nor the kernel. Two records are folded into
this one, because neither was ever committed and neither survives its own argument: 0005 made a script `exec`ed
rather than imported, one file per unit, and 0007 made discovery a plugin point a unit could contribute to. The script
track was the only prospective consumer of both.

NeoForge's own orchestration is the timeline these phases land on, because it is what calls the mod: construction
(where `DeferredRegister`s are made and bus listeners are added) → `RegisterEvent` per registry →
`FMLCommonSetupEvent` and one of `FMLClientSetupEvent`/`FMLDedicatedServerSetupEvent`, all three parallel-dispatched
→ `FMLLoadCompleteEvent` → the game, where a server starts and stops and where datapacks reload. Two buses, two axes
(`Dist` and time), and one pattern worth naming: `DeferredRegister` queues something and lets the phase apply it.
FML never unloads a mod, and the line between what a reload may change (data) and may not (registries) is
Minecraft's own.

Measured on the shipped runtime (`runs/client/python/bin/python3.13`, CPython 3.13.18): a directory given a package
name and a `__path__` executes its `__init__.py` and serves submodules and relative imports, with `__file__` naming
the file; a `.pyz` holding `<name>/__init__.py` does the same through `zipimport` with `sys.path` untouched, and
`__file__` names the archive and the member; a `.pyz` whose root *is* the package root serves submodules, never
executes its `__init__.py`, and `find_spec(name)` returns nothing; and an edit that keeps a file's byte size inside
the same second is served from a stale `.pyc` until bytecode writing is off or `__pycache__` is cleared.

## Decision

- **One owner per phase.**

  | Phase | Owner | Does | Leaves alone |
  |---|---|---|---|
  | bootstrap | `HerePy` | starts the host thread and its loop, fills `env` (`dist`, game directory, versions), attaches the event and command bridges, injects Java classes | any layout |
  | discover | kernel | scans `<game directory>/mods` for `*.pyz` and unit directories, and answers candidates carrying the identity their manifest declares | the scripts root |
  | load, register, enable | whoever discovered it | imports it, checks its manifest, opens its context, collects its markers, enables it | the messages a player reads |
  | the script pack | ScriptiveSupport | builds the package, imports it, reports what failed, keeps what it loaded | the kernel's registrations |
  | lifecycle | kernel | calls the markers it collected, from the server events it listens to | what those functions do |

- **The kernel ships one source and no plugin point.** `add_source`, "a source belongs to the unit that contributed
  it", and the fixed-point rounds they imply exist for one consumer and cost the kernel a registry plus two rules
  it would otherwise lack. What stays is one source over `<game directory>/mods` and the verbs a caller needs to
  load something itself (`active`, `enable`, `revoke_all`). The plugin point of 0007 ended here; the half of it that
  survives — a container is a directory that happens to be one file — becomes the shape of `__path__`, which takes a
  directory or a `.pyz` and leaves the rest to zipimport.
- **A script pack is a package, imported, and the whole pack is one unit.** The scripts root receives a package
  name (`herecraft_scripts`), and its `__init__.py` runs through a spec built from that file with the root as its
  `submodule_search_locations`. Relative imports work, submodules exist, ordering is the order the author imported
  things in, and a reload purges the prefix and executes again. `sys.dont_write_bytecode` is on before the first
  import, because the measured failure is an edit of the same byte size inside the same second. The exec-and-one-file
  rule of 0005 ended here.
- **The pack's identity is fixed and declares nothing.** It sits at `<game directory>/python/scripts`, a sibling of
  the runtime tree's own `lib/`, `bin/`, `share/` and `include/` — the directories the materializer replaces, which
  leaves `scripts/` in place and out of the pinned artifact. Its identity is `local/scripts` at version
  `0.0.0+local`: the namespace is `local` because nothing published it, and the name is `scripts`, an identity
  rather than a path. Its `api` goes unchecked, because it has no manifest to declare one in and it imports
  `herecraft` itself, so a mismatch fails as an `ImportError` in the file that made it. A `.pyz` under `mods/`
  carries a manifest and is a unit; a file under the scripts root is a script. The two keep their own shapes.
- **A unit's code runs where a marker puts it, and the module level is the common phase.** The markers are
  `@on_client`, `@on_server_start(server)` and `@on_server_stop(server)`. The names stay asymmetric on purpose: one
  answers a question about the distribution, the others about the game, and one shape for both invites the
  confusion 0017 refuses.
- **Loading happens while the mod is constructed, and the constructor waits for it.** Java waits on a latch the
  bootstrap releases after the last unit is enabled, because the alternative is a server that starts while units
  are still loading, with a unit's server lifecycle handler arriving after the event it was written for — measured
  in the dev client, where a pack needing 17 s to load put `ServerStartingEvent` nearly half a minute ahead of the
  units. Configuration the loader reads is a `ModConfig.Type.STARTUP` config, which NeoForge reads that early.
  `FMLCommonSetupEvent` would put the host loop on a parallel dispatch worker.
- **Reload belongs to the script track; the swap belongs to the kernel.** What to reload, when, and what its
  `/scriptive reload` command says is ScriptiveSupport's. The order of the swap is the kernel's, because the kernel
  sees both the dispatch table and the bus counts: the old handlers leave the table synchronously, the new
  incarnation loads and enables, and the old scope is released afterwards. The listeners for the events a unit used
  stay on the bus throughout, and the unit's handlers are absent only while its own load runs — which is why a
  reload is not a hot swap and is not described as one.
- **A command is a registration like any other, made from Python.** It belongs to the unit that made it and goes
  with it, so the jar carries no command name: with no script support installed there is no `/scriptive` command at
  all. The command API therefore sits on the script track's critical path, and the game rebuilds the dispatcher on
  every server start, so the bridge keeps the declarations and replays them.

## Consequences

- The shim file is gone, and each phase has one named owner, so "why did nothing load" has one place to look per
  source.
- A script pack gains the import system: submodules, relative imports, and tracebacks naming file and line. It loses
  the per-file error boundary, because one pack is one unit and one syntax error takes the pack down.
- `sys.modules` holds the pack, so a reload purges by prefix; the measured trap is an edit of the same byte size
  inside the same second, which is why bytecode writing is off for the pack.
- `__init__.py` is the entry rather than `main.py`, because `__name__` there is the package's and the guard every
  Python author writes would silently skip.
- A `.pyz` wraps the package in a directory named after it, because a flat archive cannot be found by name and its
  `__init__.py` never runs.
- A unit is imported under `herecraft_unit_<id with separators flattened>`, a plain top-level name rather than
  `0003`'s `herecraft_mods.<…>`: a parent package would exist only to exist, and an archive's directory has to
  carry the name anyway.
- A missing scripts root is an ordinary state: one line says so and the unit loads with nothing to run.
- A reload measured against a counting stand-in for the bridge moves the counts retain 1 → retain 2 → release 1,
  and the dispatch table afterwards holds only the new incarnation's handler.
- ADR 0008's companion unit is what this record makes concrete, with two of its consequences changed: there is no
  per-file error boundary, and the script track needs no `dependencies` for load order, because the unit that owns
  the pack loads it.
- The manifest fields carry upstream wording: `api` is FML's `versionRange`, `dependencies` is its `ordering`.
- How the two released files are built, versioned and published is 0019: the jar carries the core, and the script
  track is a file of its own.

## Alternatives considered

- **Unit-contributed sources.** They serve one consumer and cost the kernel a registry, an ownership rule and
  iterative discovery rounds.
- **`exec` per file.** Isolation from `sys.modules` mattered while reload was undefined; purge-and-import covers it,
  and the cost is no submodules, no relative imports, a hand-rolled ordering rule and a per-file registry.
- **A `main.py` entry.** It looks like the file to run and is not: `__name__` is the package's, so the guard every
  Python author writes is false and silently skips.
- **`import *`.** The side effects come from the import, and a star import spills the author's names into the
  library's namespace.
- **`sys.path.insert` over the scripts root.** The folder name becomes an import statement, which is the shadowing
  problem 0003 was written about.
- **Loading inside `FMLCommonSetupEvent`.** It looks like the mod's own second phase, and it puts the load on a
  parallel dispatch worker.
- **A kernel reload verb for every source.** A `.pyz` is not edited in place, so nothing else wants one, and it
  would put a registry of loaded units in the kernel for a single feature.
- **A Java-side `/scriptive reload` calling a fixed Python entry name.** The jar would carry a command it does not
  implement and a string the `.pyz` has to match.
- **A marker per phase, `@on_common` included.** It makes the module body a second place code can run at load time,
  with an ordering question between the two.
- **Letting the script track pick its own swap order.** The dispatch table and the bus counts live in the kernel,
  and an ordering rule enforced from outside is one the next caller can skip.
