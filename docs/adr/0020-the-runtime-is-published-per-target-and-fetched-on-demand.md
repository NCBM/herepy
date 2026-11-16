# 20. The runtime is published per target and fetched on demand, and a runtime on disk is used first

**Status**: proposed, 2026-11-17.

## Context

0014 pins the runtime as an artifact and states what the shipped shape removes; 0015 gives every target its own
runtime and publishes only a target that booted; 0016 settles how the Windows target is built and smoked and leaves
whether Windows ships as a product decision. This record takes that decision: the runtime is delivered beside the
mod's file, on its own, per target.

The runtime is the part of a HerePy install measured in tens of megabytes — 48 MB packaged for POSIX, 24.8 MB for the
Windows archive (0015). Inside the jar it becomes one jar per platform, or one jar that is wrong for most players, and
every runtime fix re-publishes the mod.

`PythonManager` asks `<game directory>/python` first and `PYTHON_HOME` second, and reports both paths when neither
answers. That order is the local-first rule this record keeps.

## Decision

- **The mod's file carries no interpreter.** One jar serves every target, and the runtime arrives as its own
  artifact.
- **A runtime on disk is used as it is.** `<gamedir>/python` answers first and `PYTHON_HOME` second; nothing is
  downloaded while a working tree is there.
- **When neither answers, this target's runtime is fetched.** The fetch names the artifact `runtime/manifest.toml`
  pins for the platform, checks it against the sha256 beside that name, unpacks it beside the game, and starts it.
- **Every target's runtime is published on its own**, from the build that booted it (0015), under the hash the
  manifest carries. A pin is a hash the manifest names, and no version here reads "latest".
- **A failed fetch leaves the machine where it was.** The instruction that stands today still stands, and the error
  names the artifact and the hash it wanted.

## Consequences

- One jar serves every platform, and a first start needs the network.
- The size appears at the download alone, so a player who keeps one runtime pays for it once.
- The hash is what makes a fetched runtime the same bytes this tree tested; a mismatch is a refusal.
- An offline machine installs by unpacking the archive by hand, which is the path local-first keeps alive.
- The log line from 0014 ("say which interpreter this is") answers which runtime a machine got.
- The dev loop is unchanged: the build materializes the tree into `runs/`, and local-first finds it.

## Alternatives considered

- **Shipping the runtime inside the jar.** One download everywhere, paid for with a jar per target, or a jar that is
  wrong for most players, and a mod release for every runtime fix.
- **A separate installer program.** One step before the game that a player has to find and run, with the mod still
  reporting "no runtime" when it is skipped.
- **Downloading packages with `pip` at runtime.** The runtime ships no resolver, and 0010 refused an unpinned
  install.
- **Refusing to start, as it does now.** An install that needs the jar alone cannot work, and the instructions cost a
  player more than the fetch.
