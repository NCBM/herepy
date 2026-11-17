# Architecture decisions

One file per decision, numbered in the order the decisions were made. A title is a claim, so the table below
reads as the current state of the design.

A decided thing stays as it was written: a change arrives as a new record that supersedes the old one, and the old
file keeps the reason it stopped being true. Status vocabulary is in
[0001](0001-decisions-are-recorded-here.md).

## The records

| # | Decision | Status |
|---|---|---|
| [0001](0001-decisions-are-recorded-here.md) | Decisions are recorded here, with what was refused | accepted |
| [0002](0002-the-java-python-boundary-is-a-versioned-protocol.md) | The Java/Python boundary is a versioned protocol | accepted |
| [0003](0003-a-unit-is-identified-by-a-manifest-not-by-its-module-name.md) | A unit is identified by a manifest, not by the module name it loads as | accepted |
| [0004](0004-loading-is-staged-and-registration-comes-last.md) | Loading is staged, and bus registration comes after every unit is loaded | accepted |
| [0006](0006-every-registration-is-revocable.md) | Every registration is revocable, and the handle belongs to the kernel | accepted |
| [0008](0008-the-script-experience-is-a-companion-unit.md) | The script experience is a first-party companion unit | accepted |
| [0009](0009-the-python-host-thread-owns-an-event-loop.md) | The Python host thread owns an asyncio event loop | accepted |
| [0010](0010-lifecycle-primitives-come-from-composat.md) | Lifecycle primitives come from composat, at the effect-scope layer | accepted |
| [0011](0011-the-jep-binding-is-pinned-to-4-4-0.md) | The JEP binding is pinned to 4.4.0 and upgraded by procedure | accepted |
| [0012](0012-the-python-surface-is-generated-from-a-spec.md) | The Python surface is generated from a spec | proposed |
| [0013](0013-the-repository-is-split-by-published-artifact.md) | The repository is split by published artifact | proposed |
| [0014](0014-the-runtime-is-a-pinned-artifact.md) | The runtime is a pinned artifact, and what is not pinned is declared | accepted |
| [0015](0015-every-target-gets-its-own-runtime.md) | Every target gets its own runtime, and only a target that booted is published | accepted |
| [0016](0016-wine-builds-and-smokes-the-windows-runtime.md) | Wine builds and smokes the Windows runtime; shipping Windows stays a product decision | accepted |
| [0017](0017-side-is-declared-by-where-code-runs.md) | Side is declared by where code runs, and a unit keeps its identity across incarnations | accepted |
| [0018](0018-each-loading-phase-has-one-owner.md) | Each loading phase has one owner, and a script pack is one unit | accepted |
| [0019](0019-the-jar-carries-only-the-core.md) | The jar carries only the core, and the script track is always a second file | accepted |
| [0020](0020-the-runtime-is-published-per-target-and-fetched-on-demand.md) | The runtime is published per target and fetched on demand, and a runtime on disk is used first | proposed |
| [0021](0021-the-stub-corpus-is-rendered-from-the-surface.md) | The stub corpus is rendered from the surface, and a patch is an overlay | proposed |
| [0022](0022-jep-imports-resolve-through-the-games-loader.md) | jep's import hook resolves a class through the game's loader | proposed |

Records 0005 and 0007 were folded into [0018](0018-each-loading-phase-has-one-owner.md), so their numbers stay
unused and every surviving reference still names the same decision. A record that has entered a commit keeps its
number and its words.

## How these were checked

The decisions that a run could settle were settled by one, on the runtime this repository ships
(`runs/client/python/bin/python3`, the interpreter ADR 0014 pins). A case lives either in the record that depends on
it or in [`tools/checks/check.py`](../../tools/checks/check.py), which the shipped interpreter re-runs:

```bash
runs/client/python/bin/python3 tools/checks/check.py
```

| Decision | What was measured |
|---|---|
| 0009 | a loop on its own thread answers `submit`, honours a `call_sync` deadline to 1 ms, drops the work it timed out on, keeps submission order over 200 submits, serves 64 concurrent sync callers, and stops |
| 0010 | `composat`'s `scope.py` loads with the standard library alone, and its revoke, dispose and reopen behaviour holds |
| 0014 | a runtime with twenty-two paths and numpy's tests removed boots the game and loads units; one jep build serves 3.13.18; `install_only`'s libpython is 250 MB against the stripped variant's 37 |
| 0015 | the packaged runtime (48 MB, no `bin/`, no `pip`, no numpy, no Tcl/Tk) boots the game with the dev tree's stub-generator baseline; a Windows tree unpacks to 69 MB; `libjep.so` needs `libpython3.13.so.1.0`; the Windows tree archives to 24.8 MB and the extracted archive passes the Wine probe |
| 0016 | Wine runs the Windows CPython and the pinned numpy wheel, imports a `.pyd` built with msvc-wine, and a Windows JVM under Wine answered `python 3.13.18`, `numpy 2.5.5`, `sum 45.0`; `PythonManager` in that JVM answered the Windows layout's `Lib`, `jep.dll` and `python313.dll` |
| 0018 | the Python-side cases are in [`tools/checks/check.py`](../../tools/checks/check.py): packages rooted at a directory and at a `.pyz`, the stale-`.pyc` trap and both cures, discovery, the `api` refusal before import, a failed load leaving nothing behind, both markers, the reload swap, and a command that goes when its unit does. The dev client logged `1 of 1 units loaded`, loaded before the server started, and put `[scriptive reload]` on the dispatcher |
| 0021 | the renderer's cases are in [`tools/checks/check.py`](../../tools/checks/check.py), on a stand-in classpath: two runs over the same classes write the same bytes with each class once, whatever order the reflection answered in, a class that leaves the set loses its stub, a member no expression can spell is left out of its class and reported, a class name no import can spell is rejected and writes nothing, a javadoc fragment turns into docstring text, a stub carries the doc the data holds — once per overload, with none at all when the data has none — and a parameter takes the name the data gives its slot, keeping `argN` where the data has none. The walk's cases are there too, on the same stand-in: the class set is what the seeds reach through bases, members, type arguments, array components and wildcard or type-parameter bounds, a nested class is rendered as the class that declares it, a class the loader lacks is reported without stopping the walk, and a run's tree holds no class it did not reach, the seeds are the names `herecraft/api` declares, the event wrappers among them, and a package with no class of its own holds only the marker |
| 0022 | a dev client, one build apart: `from net.minecraft.world.item import ItemStack` and `from net.minecraft.world.level.block import Blocks` end in `ClassNotFoundException` without the config and import with it, `Blocks.STONE` reading `Block{minecraft:stone}` at unit load. Under a plain JVM over jep 4.4.0, a loader shaped like a mod loader resolves a class no other loader can see, jep's proxies keep working through it, and an enquirer that answers for one package alone takes `java` with it |