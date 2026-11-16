# HerePy

A NeoForge mod that puts a CPython 3.13 interpreter inside the game. The mod embeds the runtime through JEP, and
`herecraft` is the package a script programs against: a unit dropped into `mods/` is loaded while the game
constructs the mod, and what it registers — event handlers, commands, the work it marks for one distribution —
goes when the unit is revoked.

NeoForge 21.1.211 on Minecraft 1.21.1, JDK 21, and the CPython runtime this repository pins (ADR 0014).

## A unit

A unit is a directory under the game's `mods/`, or an archive that holds one, and either way it is a package: a
`manifest.toml` at its root states the id, the version and the api series the unit was written for, and
`__init__.py` is its entry. The id decides the name the unit is imported under, so the directory name stays out of
the import system.

The api series is checked before the import, so a unit from another series is refused with both sides named. A
unit that raises while loading leaves nothing behind, and the units beside it carry on loading.

## What a script gets

| name | what it is |
| --- | --- |
| `herecraft.event` | `@event` registers a function as a handler for the event its first parameter is annotated with, and a handler may be a coroutine. `@event(sync=True)` marks the handler whose decision the game thread waits on — cancelling an event — and that wait carries a deadline. |
| `herecraft.markers` | `@on_client` marks work that runs after the unit has loaded, on a distribution that has a client; `@on_server_start` and `@on_server_stop` arrive as ordinary handlers, handed the server. |
| `herecraft.commands` | `@command("some path")` puts a literal path on the dispatcher, and the function is handed the command source. |
| `herecraft.api` | `Player`, `Level`, `BlockPos`, `ItemStack` and the rest, plus `herecraft.api.events` for the events a handler can name. |

`herecraft` reaches Java through the mod's own seams: an event crosses by class name, a command by the path it was
given, and both cross to the loop the mod owns.

## The script track

`src/units/scriptive-support` is the first-party unit. It imports `<game directory>/python/scripts` as a single
pack, so a directory of scripts is one unit and what any of it registers comes back together, and it offers
`/scriptive reload`, which drops the pack's modules and loads it again.

## Building and running

```bash
./gradlew materializePythonRuntime   # the dev runtime, under runs/client/python
./gradlew runClient                  # the game, with that runtime beside it
./gradlew build                      # the jar
```

The runtime arrives from `runtime/manifest.toml`, which states what it contains, and `gradle/python-runtime.gradle`
applies it (ADR 0014). The units in `src/units` are copied into each run directory's `mods/` before that run
starts, so the dev loop goes through discovery and the manifest check the way a release does.

The Python half runs without Minecraft:

```bash
runs/client/python/bin/python3.13 tools/checks/check.py
```

## What this is not

- **A sandbox.** A unit runs in the game's own process with the interpreter's whole reach: it can import `java.*`
  and call what the game has loaded.
- **A source of its own choosing.** The kernel reads `<game directory>/mods`, which is the one source there is
  (ADR 0018).
- **A hot swap.** A reload detaches the unit's handlers, loads the new incarnation and enables it, so the events
  that arrive while its own load runs are missed. The listener for an event class stays on the bus throughout.
- **A queue for slow handlers.** A synchronous handler is a game-thread stall, bounded by the dispatch deadline; a
  handler that needs longer belongs in an asynchronous one.

## Documentation

| file | what it holds |
| --- | --- |
| `docs/adr/` | the decisions, one claim per file, with what each refused — the reason a shape is what it is |
| `AGENTS.md` | the map: the commands, and the file each answer lives in |
| `tools/checks/check.py` | the claims a run can settle, re-run against the shipped interpreter |
