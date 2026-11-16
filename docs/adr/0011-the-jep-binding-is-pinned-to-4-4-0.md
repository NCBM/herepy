# 11. The JEP binding is pinned to 4.4.0 and upgraded by procedure

**Status**: accepted, 2026-11-16.

## Context

`gradle.properties` pins `jep_version=4.2.2` (2024-12-15) and `build.gradle` resolves it as
`black.ninia:jep`. Four releases have happened since, and the middle one changes things this project
depends on:

- **4.3.0** — the Maven groupId moved to `org.ninia`; `PyConfig` was rewritten to map onto PEP 587
  (`new PyConfig()` and `setPythonHome(String)` are deprecated, `PyConfig.python()`/`setHome(String)`
  replace them); Python below 3.10 is dropped; numpy became a build requirement; `Interpreter.attach`
  lets further threads join one interpreter; all types became heap types.
- **4.3.1** — fixes a regression 4.3.0 introduced in accessing Java **subpackages through attributes**.
  `herecraft` does this throughout (`from java.lang.reflect import Type`, `from com.mojang.logging
  import LogUtils`, `from java.util.jar import JarFile`), so 4.3.0 is not a version to sit on.
- **4.4.0** — adds `jep.PythonException` (a `JepException` carrying the Python stack and the original
  exception's `PyObject`), fixes two rare leaks, and deprecates **shared modules**
  (`JepConfig.setSharedModules`), not `SharedInterpreter` — the release notes name `SharedInterpreter`
  as the migration target.

## Decision

- Resolve `org.ninia:jep:4.4.0`. It is verified that `black.ninia:jep:4.4.0` holds only a relocation POM
  and no jar, so changing the version without changing the coordinate fails to resolve rather than
  falling back.
- `PyConfig.python()` + `setHome(...)`; the deprecated `setPythonHome` and the no-argument constructor
  are not used in new code.
- `SharedInterpreter` stays: it is what the shared-modules deprecation points at.
- Sync dispatch distinguishes `PythonException` and logs the Python traceback, instead of logging a
  `JepException` cause that says nothing about where in Python it broke.
- Upgrading is a procedure, not a version bump: jep publishes an sdist only (no wheels, verified on
  PyPI for 4.4.0), so the upgrade means building it inside the embedded runtime, and 4.3+ needs numpy
  present to build. The runtime this repository carries
  (`runs/client/python/lib/python3.13/site-packages`) has `pip` and `jep` and **no numpy**.

## Consequences

- The upgrade has an ordering constraint: numpy into the embedded runtime, then jep, then the mod.
- The `LD_PRELOAD` line in `build.gradle` is an absolute path to one machine's checkout; it is a
  separate defect, but it is the same class of problem as the hand-maintained runtime, and pinning jep
  in a runtime manifest is where both get fixed.
- 4.3's isolated-subinterpreter work and `attach()` make "one interpreter, several threads" an
  officially supported shape — which ADR 0009 uses.

## Carried out, 2026-11-16

What changed in the tree: `jep_version` in `gradle.properties`, both coordinates in `build.gradle`,
`PyConfig.python()` + `setHome(...)` in `HerePy.java`, and `PythonException` handling in
`EventBridge.registerSyncListener`.

What the runtime needed, and what it cost:

- numpy first (4.3 makes it a build requirement): `pip install numpy` into
  `runs/client/python`, which had none. Installed 2.5.5.
- then jep, from the sdist, **with `LDFLAGS=-L<runtime>/lib`**. This Python distribution records
  `LIBDIR` as `/install/lib`, a path that never existed on this machine, so the link step asks for
  `-lpython3.13` in a directory with no libraries in it and fails with
  `ld: cannot find -lpython3.13`. The flag only has to make the real directory reachable.
- `libjep.so` and `jep-4.4.0.jar` land in `site-packages/jep/`, which is where
  `PythonManager.getJepLibPath()` looks; `pip show jep` answers 4.4.0.

What the build needed: `./gradlew build` is green, and `org.ninia:jep:4.4.0` resolves on
`compileClasspath`. The first attempt failed three tasks in, on
`create1.21.1ClientExtraJar`, for a reason that predates this change:
`.gradle/caches/minecraft/versions/1.21.1/client.jar` was a zip with no end-of-central-directory
(its content dates from 2024-08-08) and the same blob sat in
`~/.local/share/gradle/caches/ng_execute/`. Deleting the file is not enough — Gradle's build cache
puts it back, so the repairing run is `./gradlew build --no-build-cache` once, with the file
removed. `archlinux-java status` lists `java-21-openjdk`, which the toolchain picks up without
changing the system default (zulu-17).

Verified at runtime the same day: `runClient` reached the main menu, a singleplayer world loaded and
quit with no crash report, and the Python half demonstrably ran — `stubgen_test` rewrote every `.pyi`
under `runs/client/python/typings/` at the moment the mod initialised, which exercises JEP startup,
`ReflectWrapper`, subpackage imports and `ast.unparse` against 4.4.0.

What that run also showed: **no Python log line reaches the game log.** The bootstrap imports
`herecraft.conversions`, `herecraft._internals.javans` and `herecraft.api._setup`, and `herecraft/__init__.py`
is empty, so `herecraft/logging.py` — the handler that forwards to SLF4J — is never imported. Importing
it fixes half of it; the other half is that `logging.basicConfig` defaults to WARNING, so that module has
to ask for INFO. Both are now done, and `[herecraft.shims] Loading unit: <name>` appears for every unit.

The same run found one more break, in dispatch rather than at startup: `event.getClass().getName()`
raises `AttributeError: 'jep.PyJClass' object has no attribute 'getName'`, because 4.3 turned every
type into a heap type and 4.4's `PyJClass` no longer proxies `java.lang.Class`'s methods — its attribute
dict holds only the represented class's own static members. Every `PyJObject` answers `java_name`
instead (jep computes it with `Class.getName()` on the object's runtime class), so the question is
asked in one place, `herecraft/_internals/java.py`, which both `herecraft.event` and
`api._registry.wrap` use, and which keeps the pre-4.3 route as a fallback.

Verified end to end afterwards: a three-line unit in `python/scripts/smoke/` registers a handler for
`ServerStartingEvent`, and loading a world produces
`[herecraft.smoke] smoke: server starting, motd='Dev - 新的世界'` — decorator, registry, bus
registration, dispatch back into Python, the wrapper, and the log route, all in one line.

A cost that showed up doing it: loading units synchronously (so the bus is populated before it is
subscribed) means a slow unit delays the whole bootstrap — the stub generator in `scripts/` adds about
twelve seconds. That is ADR 0004's problem, and it now has a number attached.

## Alternatives considered

- **Stay on 4.2.2.** Misses the leak fixes and the subpackage fix, and the embedded runtime is the one
  place where a slow leak is a crash after a few hours of play.
- **Take 4.3.2 instead of 4.4.0.** Same coordinate change, one less fix; there is no reason to stop
  short.
- **`black.ninia:jep:4.4.0` to avoid touching the coordinate.** Verified not to work: the artifact at
  that coordinate is only a relocation POM.
- **Build jep without numpy by editing its `pyproject.toml`**, as its notes describe. Removes a build
  prerequisite and makes the build unreproducible in a way the next person will not reproduce.
