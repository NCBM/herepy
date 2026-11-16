# AGENTS.md

HerePy is a NeoForge mod (Minecraft 1.21.1, JDK 21) that embeds a CPython runtime in the game through JEP;
`herecraft` is the Python package a script unit programs against.

This file is a map, not a manual. The reasoning lives in [`docs/adr/`](docs/adr/README.md), and anything here
that restates it is a bug in this file.

## Commands

```bash
./gradlew build          # the mod jar
./gradlew runClient      # dev client, needs the runtime below
./gradlew runServer
./gradlew runData
```

```bash
runs/client/python/bin/python3.13 tools/checks/check.py   # the Python half, no Minecraft needed
./gradlew installUnits          # src/units -> each run directory's mods/, where discovery reads them (ADR 0018)
./gradlew materializePythonRuntime            # dev runtime: full base + packs, herecraft symlinked into src/
./gradlew materializePythonRuntime -Ppackage  # the shipped shape: removals applied, precompiled, no packs
./gradlew packagePythonRuntime                # after -Ppackage: build/dist/<name>.tar.gz + .sha256
./gradlew checkPythonRuntime                  # manifest against what is on disk

./gradlew wineJepSmoke -PwinJdk=<dir>           # Windows target: build it with cl, smoke it under Wine (ADR 0016)
./gradlew wineJepSmoke -Ppackage -PwinJdk=<dir> # the shipped shape again, for the Windows layout
./gradlew packageWindowsRuntime -PwinJdk=<dir>  # archive it, then boot the archive itself under Wine
```

```bash
ruff check src/herecraft/ && ruff format --check src/herecraft/ && basedpyright src/herecraft/
```

## Where the truth is

| What you need to know | Where it is written |
|---|---|
| why anything here is the way it is | [`docs/adr/`](docs/adr/README.md) — one claim per file, with what was refused |
| which claims are checked, and how to re-check them | `tools/checks/check.py`, named by the evidence table in [`docs/adr/README.md`](docs/adr/README.md) |
| what the embedded runtime contains, per platform | [`runtime/manifest.toml`](runtime/manifest.toml) (ADRs [0014](docs/adr/0014-the-runtime-is-a-pinned-artifact.md), [0015](docs/adr/0015-every-target-gets-its-own-runtime.md)) |
| how the runtime is fetched, trimmed, precompiled and archived | [`gradle/python-runtime.gradle`](gradle/python-runtime.gradle) |
| building and smoking the Windows target without a Windows machine | ADR [0016](docs/adr/0016-wine-builds-and-smokes-the-windows-runtime.md) |
| how the mod finds the runtime's files, in either layout | ADR [0016](docs/adr/0016-wine-builds-and-smokes-the-windows-runtime.md), [`PythonManager`](src/main/java/top/nhanchou/herepy/pythonrt/PythonManager.java) |
| Python lint and type rules | [`pyproject.toml`](pyproject.toml) |
| threads, the loop, and the only way into Python from Java | ADR [0009](docs/adr/0009-the-python-host-thread-owns-an-event-loop.md) |
| what a unit is, and how it is taken back | ADRs [0003](docs/adr/0003-a-unit-is-identified-by-a-manifest-not-by-its-module-name.md), [0004](docs/adr/0004-loading-is-staged-and-registration-comes-last.md), [0006](docs/adr/0006-every-registration-is-revocable.md) |
| who owns each phase of a load, and what a script pack is | ADR [0018](docs/adr/0018-each-loading-phase-has-one-owner.md) |
| which side a unit's code belongs to, and what a reload keeps | ADR [0017](docs/adr/0017-side-is-declared-by-where-code-runs.md) |
| the Java/Python boundary as a protocol | ADR [0002](docs/adr/0002-the-java-python-boundary-is-a-versioned-protocol.md) |
| how a decision gets made or changed | ADR [0001](docs/adr/0001-decisions-are-recorded-here.md) |
