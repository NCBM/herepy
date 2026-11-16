# HerePy

A NeoForge mod that puts a CPython interpreter inside the game. The interpreter arrives through JEP, and `herecraft`
is the package a script unit programs against: a unit dropped into the game's `mods/` registers events, commands and
the work it marks for one distribution, and what it registered leaves when the unit is revoked.

```bash
./gradlew materializePythonRuntime   # the dev runtime, under runs/client/python
./gradlew runClient                  # the game, with that runtime beside it
./gradlew build                      # the jar
```

## Where the truth is

| what you need | where it is |
| --- | --- |
| the surface a unit programs against, and why each seam has its shape | `src/herecraft/`, in the docstring of the module that owns it |
| the first-party unit that reloads a pack of scripts | `src/units/scriptive-support` |
| the decisions, one claim per file, with what each refused | `docs/adr/` |
| every command, and the file each answer lives in | `AGENTS.md` |
| the claims a run can settle | `tools/checks/check.py` |
| the coordinates this build targets | `gradle.properties` |
| the pinned runtime, per platform | `runtime/manifest.toml` (ADRs 0014, 0015) |
