# 14. The Python runtime is a pinned artifact, and what is not pinned is declared

**Status**: accepted, 2026-11-16.

## Context

`runs/client/python` holds the interpreter the mod embeds, and it held 279 MB of files with no record of
where they came from. Its provenance had to be measured by hand — CPython 3.13.3, Clang 20.1.0,
`--prefix=/install`, which matches python-build-standalone's tag `20250409` — and nothing in the
repository said so. Rebuilding it was a matter of remembering which commands had been run.

Three costs had already been paid for that:

- ADR 0011's `-lpython3.13` failure came from `sysconfig` answering `LIBDIR=/install/lib`, a path that
  exists on no user's machine. It is a feature of the artifact, not a mistake in the build script.
- The runtime drifted by addition: numpy 2.5.5, jep 4.4.0 and typing_extensions 4.16.0 were installed by
  hand, and pip came along with the artifact while nobody decided it should ship.
- `lib/python3.13/herecraft` is a symbolic link into `src/`. An archive cannot carry it, so the packaged
  runtime would have been built from something the dev tree never tested.

What the bytes are, measured: libpython 37 MB, numpy 57, pip 12, stdlib 20, Tcl/Tk 9, terminfo 12,
`include/` 2.4, `bin/` 2.1, jep 3.7 — of a 279 MB dev tree that also carried 120 MB of generated `.pyi`.

## Decision

**The runtime is one pinned artifact plus declared patches, and a manifest is the only thing that says
what is in it.**

- The base is a python-build-standalone release, pinned by tag, asset name and sha256, one asset per
  platform, of the `install_only_stripped` variant. Never `latest`: the project publishes every one to two
  weeks, so a moving pin is a pin that changes without a diff.
- `runtime/manifest.toml` names the base, what the shipped package removes from it, and every addition
  with its own sha256. A Gradle task materializes `runs/client/python` from that manifest; nothing in the
  runtime is installed by hand, and "why is this file here" has an answer in the repository.
- Additions are **overlay packs**: archives laid out like the runtime and unpacked at its root, so one
  rule describes the base and its patches, and a patch is a thing a user can choose.
- **numpy is an overlay, not part of the base.** It costs 57 MB and no line of `herecraft` imports it; what
  it buys is a unit author's arithmetic, which is worth having and not worth forcing on everyone. As an
  overlay it is 49 MB on disk and 13.5 MB compressed, with the package's own `tests/` left out.
- **pip is removed from the shipped runtime.** A unit's imports are the manifest's business, and a
  `pip install` into a game directory at run time is neither reproducible nor safe. pip stays in the dev
  runtime, where it is how the overlays get built.
- **The standard library is not pruned** beyond what cannot work embedded (`tkinter` and its Tcl/Tk,
  `idlelib`, `pydoc`, `ensurepip`, `turtle`, `_pyrepl`, debugging conveniences). The whole thing is 20 MB
  and less than 3 MB of it is plausibly unused, so pruning it would trade surprise breakage in a unit for
  nothing measurable.
- **The archive format is `tar.gz`.** It is what the project publishes, so the download-and-verify step
  works on the upstream asset rather than on a transcoding of it, and the JDK reads gzip with no
  dependency at all (`GZIPInputStream`); only the tar walk has to be ours, and it only has to read. The
  numbers behind that are under the rejected zstd and zip, which are the two alternatives that look
  cheaper than they are.

The pin as it stands: `20261110` / CPython `3.13.18` / `install_only_stripped`, e.g.
`cpython-3.13.18+20261110-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz`, sha256
`f2d2199eb25880e07863b391cf7124e7ffa1338b0d65600dfcec117c4223a7fb`, 35,696,130 bytes.

## Rejected

- **The `install_only` variant.** It publishes the same interpreter with a 250 MB libpython, 280 MB
  unpacked, for no benefit to us: the difference is debug information and nothing else. The variant is
  worth one line in the manifest precisely because it is easy to pick the wrong one.
- **Building CPython ourselves** to drop the test extensions. The current artifact already did it: 43
  `_test*` modules in 3.13.3's libpython, 2 in 3.13.18's. Owning a CPython build is a large commitment to
  save what someone else already saved.
- **Pruning the standard library** — see above. It buys under 3 MB and spends the promise that a unit can
  import what Python has.
- **Shipping the dev tree.** Its 120 MB of generated stubs, the symlinked `herecraft`, pip, and a libpython
  chosen by whoever initialized it once, are all things the package should not contain.
- **zstd, or zip, as the runtime archive.** Measured on the trimmed 44 MB tree: 13.67 MB at gzip -6, 13.57
  at gzip -9, 13.45 at zstd -3, 11.00 at zstd -19, 9.98 at xz -9, and 24.42 at zip -9. zstd's default
  level is 1.6% ahead of gzip and its maximum is 19%, and the JDK has neither zstd nor xz — so either one
  is a decoder we ship, and `zstd-jni` is a native library per platform inside the mod jar, which turns
  "compression algorithm" into a startup failure surface, bought for 2.6 MB. zip is the opposite mistake:
  it needs no dependency and costs 79% more, because it compresses file by file with no solid block over a
  tree full of near-identical small `.py` files.

## Carried out, 2026-11-16

The runtime was swapped from 3.13.3 (`20250409`) to 3.13.18 (`20261110`), and the swap was the first test
of the pin: nothing else changed, and everything kept working.

- **jep did not need rebuilding.** `jep.cpython-313-*.so` and `libjep.so` both link
  `libpython3.13.so.1.0`, whose name does not change inside a minor, and the extension module resolves 177
  `Py*` symbols at load. That is an argument, not a proof: jep refuses to import outside a JVM
  (`Jep is not supported in standalone Python, it must be embedded in Java`), so the only way to settle it
  was to boot the game, which is what was done.
- **3.13.18 is smaller where it counts.** libpython 31 MB against 37, because the new build drops the test
  extensions (PyInit 136 → 92). Its `bin/python3.13` is a 31 MB statically linked executable
  (`--enable-static-libpython-for-interpreter`) rather than a 2 MB launcher — which is free for us, since
  the shipped runtime removes `bin/` entirely. Same trim list on both trees: 47 MB from 3.13.3, 44 MB from
  3.13.18.
- **The trim list is measured, not guessed.** Park twenty-two paths — `share/`, `include/`, `bin/`,
  Tcl/Tk and its Python side, pip and `ensurepip`, `idlelib`, `pydoc*`, `turtledemo`, `turtle.py`,
  `_pyrepl`, `doctest`, `config-*`, `pkgconfig` — plus numpy's `tests`, boot the game, and it behaves: host
  thread up, units loaded, stub generator ran, no `No module named` anywhere. 279 MB → 104 MB with numpy,
  55 MB without.
- **The manifest is that list, written down.** `runtime/manifest.toml` carries the pin, the removals and the
  numpy pack; applying its removals to a fresh 3.13.18 tree gives 45 MB, so the specification and the
  experiment agree. Three of its patterns match nothing in this artifact, because Tcl/Tk is 8.6 in one and
  9.0 in the other.
- **The task is those two paragraphs, executable.** `./gradlew materializePythonRuntime` fetches the pinned
  asset, verifies its sha256, extracts it, carries an existing `jep` across the swap, unpacks the packs and
  makes the `herecraft` link; `-Ppackage` applies the removals, precompiles (`compileall`, 1074 modules) and
  copies the sources instead of linking them. Both modes were booted. The dev tree is 157 MB, the shipped one
  48 MB, and the shipped one runs the mod with no `bin/`, no `pip`, no numpy, no Tcl/Tk and no `No module
  named` anywhere.
- **What ships is what was tested.** `./gradlew packagePythonRuntime` writes the archive a release would
  publish — 19.1 MB, 1228 entries, symlinks and modes preserved, sha256 beside it — and that archive, extracted
  over the runtime directory, was the thing that booted. ADR 0015 records the numbers and the load-path change
  that made an environment variable unnecessary.
- **Two facts worth keeping.** `strip` on the stripped artifact's libpython saves 2 MB (37 → 35), so the
  variant really is stripped and there is nothing to gain there. And the artifact ships no `__pycache__` at
  all, so a packaged runtime would write `.pyc` files into its own install directory on first import unless
  we precompile.
- **One correction.** An earlier version of this section claimed `share/terminfo` was deduplicated by hard
  links and grew from 7.2 MB to 12 MB when expanded. It is not: the tarball carries 1048 *symbolic* links
  and no hard links, and both trees hold identical bytes (2,201,663 of them). The 7.2/12 difference was
  `du` counting blocks on a tmpfs tree against a disk tree. Sizes measured across filesystems are not
  comparable, which is worth knowing before trusting any number in this record.

What this record still owes:

- The Windows and macOS trim lists. The manifest's list was measured on linux and says so; those trees lay
  themselves out differently (`python.exe`, `DLLs/`, `Lib/`) and have to be measured the same way rather
  than translated.
- jep's build. It is sdist-only on PyPI, so it cannot be pinned as a binary and has to be compiled against
  this very runtime; until that is a step the task performs, an existing installation is carried across and
  its absence is reported. Which is ADR 0011's open question wearing a different hat.
- The packs as published artifacts: today a pack is a pinned wheel unpacked at build time, not an archive of
  our own with its own sha256.
- The packs as published artifacts: today a pack is a pinned wheel unpacked at build time, not an archive of
  our own with its own sha256.
