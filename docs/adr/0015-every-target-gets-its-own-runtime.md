# 15. Every target gets its own runtime, and only a target that booted is published

**Status**: accepted, 2026-11-16.

## Context

ADR 0014 pinned the runtime as one artifact and one manifest. The pin already names six assets, one per
platform, but everything around it — the removal list, the jep build, the way the library is found at load
time, the way the mod locates the tree — is the Linux shape. That shape was measured on Linux and nowhere
else, so "the runtime" is currently one target wearing the word *the*.

Measuring the second family of layouts was worth the download, because it is not a translation of the first.
A Windows tree unpacks to 69 MB (105 MB on Linux) and has almost nothing in common with it:

| | POSIX (Linux, macOS) | Windows |
|---|---|---|
| the interpreter | `lib/libpython3.13.so` / `.dylib`, 31 MB | `python313.dll`, 5.9 MB, plus `python.exe` |
| extensions | linked into libpython | separate `.pyd` files in `DLLs/` |
| the standard library | `lib/python3.13/` | `Lib/` |
| Tcl/Tk | `lib/tcl9.0`, `lib/tk9.0`, `lib/libtcl9.0.so` | `tcl/` 11 MB and `DLLs/{tcl86t,tk86t}.dll` |
| link inputs for a C extension | `include/` + `lib/libpython3.13.so` | `include/` + `libs/python313.lib` |
| leftovers this artifact still carries | — | `DLLs/_test*.pyd` (700 KB), `Lib/__pycache__` (2.7 MB) |

Three things follow, and none of them is a packaging detail:

- **jep cannot be fetched, only built.** It is sdist-only on PyPI, so every target compiles it against its own
  interpreter: gcc and a shared libpython here, MSVC and `python313.lib` there, Xcode and a dylib elsewhere.
  The pin in ADR 0011 is the sdist's sha256; the binary that comes out is per target and shares nothing.
- **The library is found today by an environment variable, which a user cannot set.** `libjep.so` needs
  `libpython3.13.so.1.0` and carries no `RPATH`; the dev run works because `build.gradle` sets `LD_PRELOAD`.
  A mod that ships to players has no such lever, so the archive has to be fixed before it ships:
  `patchelf --set-rpath '$ORIGIN/../../../lib'` on Linux, `install_name_tool -add_rpath
  @loader_path/../../../lib` on macOS, and `python313.dll` beside `libjep.dll` on Windows, where the loader
  looks in the module's own directory first. (`libjvm.so` needs no such care: the JVM already has it loaded,
  and the dynamic linker resolves a needed soname against what is in the process.)
- **Only one target can be booted here.** Starting the game is the only check that has ever proved a runtime
  works — it is what caught the jep ABI question in ADR 0014 — and it exists only for Linux x86_64.

## Decision

**A target is `<os>-<arch>`, and a target is the unit of building, verifying and publishing.**

- Each target owns its base asset, its removal list, its jep build, its load-path fixup and its archive. None
  of these is shared, derived, or translated from another target.
- **Only a target that booted is published.** "Booted" means what it meant for Linux: the game starts, the
  units load, the stub generator runs, and the log has no `No module named`. A target that can only be
  import-tested is not released, however much the import test passed; it is a target we have not built.
- A target's jep build is a step inside that target's build, with that target's toolchain, headers and link
  libraries. It is not a download and not a second artifact.
- **No environment variable is ever required of a player, and the archive needs no patching either.** The mod
  loads the interpreter itself, by absolute path, before jep goes looking: `libjep.so`'s `NEEDED` entry is
  then satisfied by a library the process already has, which is the trick `LD_PRELOAD` was playing and the one
  reading that is identical on all three platforms. (`patchelf`, `install_name_tool` and a DLL beside
  `libjep` were the first answer here; loading from Java makes all three unnecessary, and two of them are
  POSIX-only tools anyway.)
- The removal list becomes per-target data in `runtime/manifest.toml`, and a target with no list fails the
  materialize task rather than falling back to the POSIX one.

Which targets, in order, and why:

| target | runner | state |
|---|---|---|
| linux-x86_64 | `ubuntu-24.04` | built, packaged at 48 MB, booted |
| windows-x86_64 | `windows-2022` | built and smoked under Wine: 27 paths removed, 34 MB runtime, archived at 24.8 MB with numpy and jep |
| macos-aarch64 | `macos-14` | not measured |
| linux-aarch64 | `ubuntu-24.04-arm` | not measured |
| macos-x86_64 | `macos-13` | not measured |
| windows-aarch64 | — (no hosted runner) | not planned |

The Windows removals, from the measured tree and **verified by the Wine smoke** (ADR 0016): `tcl/`,
`DLLs/{tcl86t,tk86t}.dll`, `DLLs/_tkinter.pyd`, `DLLs/_test*.pyd`, `Lib/{tkinter,idlelib,turtledemo,turtle.py,
venv,pydoc_data,ensurepip}`, `Lib/site-packages/pip*`, `include/`, `libs/` — the last two only *after* jep has
been built, which is the ordering the POSIX list also hides. Twenty-seven paths, and the tree goes from 69 MB to
34 MB; with numpy (a pack, 37 MB on disk here), jep (0.9 MB) and the precompiled bytecode, the shipped shape is
80 MB on disk and 24.8 MB as a tar.gz.

## Consequences

- Six builds where there was one, and five of them unverifiable in this workspace. The honest reading is that
  the project supports one target today and has a measured plan for a second.
- Windows x86_64 is where most players are, so it is the target worth spending the first unverifiable build
  on — and the one that will teach the most, because it shares neither the layout nor the toolchain.
- Every target's jep build is a place to drift from ADR 0011's pin, and a place where the compiler that made
  the interpreter and the compiler making the extension can disagree. The sdist sha256 keeps the source
  honest; nothing keeps the ABI honest except the boot.
- The dev tree stays whatever the developer's machine is. It is not the shipped tree, and the shipped tree is
  not what was developed against — which is why the packaging step has to boot its own output.
- `PythonManager`'s "find `lib/python3.x` under `python/`" was POSIX logic that happened to be in Java; it reads
  the layout off the tree now, because the Windows layout is built (§0016).

## Alternatives considered

- **One POSIX runtime, Windows unsupported.** The cheapest thing that ships. It refuses the platforms where
  most of the players are, in a mod whose whole point is that a script author should not care what the
  machine is.
- **Translate the POSIX removal list to Windows.** A pattern-matched list for a layout that was never
  measured is how a runtime loses the one file a unit needs three weeks later. The list is cheap to measure
  and expensive to guess.
- **Ship the raw artifact and let the client decide.** It moves the jep compile and the load-path fixup onto
  the player's machine, which needs a compiler there and a toolchain that matches the interpreter's.
- **Cross-compile jep.** It links against the target's libpython and is loaded by that interpreter; a
  compiler that does not share the target's ABI produces a library that loads and then misbehaves, which is
  the worst of the three outcomes.
- **Publish import-tested targets and mark them experimental.** It publishes something whose only failing
  mode is on a player's machine, and it makes "booted" mean less than it does here.

## Carried out, 2026-11-16

Linux x86_64, and — under Wine only — Windows x86_64:

- `./gradlew materializePythonRuntime -Ppackage` produces the shipped shape: 48 MB, no `bin/`, no `pip`, no
  numpy, no Tcl/Tk, `herecraft` copied rather than linked. Booting the game against it logged
  `Python 3.13.18`, all three units, the stub generator's `3900 ok, 83 failed` — the same baseline as the dev
  tree — and no `No module named`.
- The shape is an archive now, not a directory: `./gradlew packagePythonRuntime` writes
  `build/dist/herepy-runtime-3.13.18-linux-x86_64.tar.gz` with its sha256 beside it — 19.1 MB, 1228 entries,
  symlinks and modes preserved. Precompiling comes first (`compileall`, 1074 modules), so a packaged runtime
  never writes into its own install directory; it costs about 5 MB of the archive, which is the price of not
  writing at run time.
- Extracting that archive over the runtime directory and starting the game logged `Python 3.13.18`, the three
  units and the same `3900 ok, 83 failed`, with **no `LD_PRELOAD` left anywhere in `build.gradle`**: the load
  path is the mod's own `System.load`, and the archive is what shipped.
- The Windows tree takes the same two steps as the POSIX one: `./gradlew wineJepSmoke -Ppackage -PwinJdk=<dir>`
  builds it and `./gradlew packageWindowsRuntime` archives it. The base asset comes from the pin, numpy from the
  pin, jep from its sdist with `cl`, the removals that take `include/` and `libs/` away come after that compile,
  `herecraft` is copied into `Lib/` — beside `site-packages`, which is where the POSIX tree keeps it, because the
  mod runs `herepy-shims.py` by path and both layouts have to agree on where that file is — and `compileall`
  comes after them, so 742 modules are bytecode before anything is archived: 80 MB on disk,
  `herepy-runtime-3.13.18-windows-x86_64.tar.gz` at 24.8 MB and 2003 entries. The archive task then unpacks what
  it packed and points the probe at that tree — it loads `jep.dll`, starts `3.13.18`, imports numpy and all four
  `herecraft` modules — and only then writes the checksum, so the archive is what the smoke passed rather than a
  copy of it. (The 22.4 MB measured earlier was the same tree archived by hand, without bytecode.)
- The archive task refuses two trees: one whose marker was not written from this manifest, and one that still
  holds a path its target's removal list names. Neither is visible in the archive afterwards, so both are
  checked before it is written.

What this record owes, in the order it becomes true:

- The Windows removal list measured the way the POSIX one was — remove, boot, look at the log — and then the
  target itself: jep built with MSVC against `libs/python313.lib`, and a game started on Windows.
- A lock file naming each published target's archive and sha256, and a mod that picks its target by
  `<os>-<arch>` instead of assuming `lib/python3.x`.
