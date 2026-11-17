# 22. jep's import hook resolves a class through the game's loader

**Status**: proposed, 2026-11-17.

## Context

`from net.minecraft.world.item import ItemStack` raised `ImportError: java.lang.ClassNotFoundException:
net.minecraft.world.item.ItemStack`. The importer is `jep/java_import_hook.py`: an attribute a package module does
not have becomes `self.__classLoader__.loadClass(name)`, and jep fills that field from `JepConfig.classLoader`.
Left unset, `Jep` uses `Jep.class.getClassLoader()`, the loader that loaded jep, which sees none of the classes a
mod loader defines. The game's classes live in the loader the game runs on.

`JepConfig.setClassLoader`, `setClassEnquirer` and `SharedInterpreter.setConfig` are public, and `jep.ClassEnquirer`
is an interface, so the hook takes another loader as configuration.

## Decision

- **The runner hands jep one config before any interpreter exists**, and its class loader is the context loader of
  the thread that starts the host thread. `SharedInterpreter.setConfig` is static and holds one config for the
  process, so a mod that made an interpreter first keeps jep's own loader; the runner reports that as a warning and
  the game runs on.
- **A unit reaches a Java class the api does not wrap by importing it.** `herecraft.api` stays the surface a unit
  programmes against, and an import is the way to a type with no wrapper.
- **The enquirer stays as jep ships it.** `java_import_hook.setupImporter` installs one importer for the process, so
  a replacement answers for every package or it takes jep's own away; one that delegates to `jep.ClassList` is the
  shape to write when a package has to be added.

## Consequences

- Measured on a dev client, one commit apart: without the config `ItemStack` and `Blocks` fail with
  `ClassNotFoundException`, and with it both import, down to `Blocks.STONE` reading `Block{minecraft:stone}` at unit
  load. Under a plain JVM over the same jep, a `URLClassLoader` whose parent is the platform loader resolves a class
  no other loader can see, and jep's own proxies keep working through it: a mod loader's shape is a shape jep
  survives.
- The hook loads and does not initialise — `loadClass` is `forName(name, false, loader)`. A class whose initializer
  needs the game runs it at first use; outside the game that answer is `Not bootstrapped`.
- A client-only class fails to import on a dedicated server, at import time, so a unit that names one at module
  level loads on one side and not the other (ADR 0017).
- Two ways to touch a game object now exist: the wrapper the api hands over, and the raw proxy an import returns.
  The second carries Java's calling conventions — `stack.getCount()`, overloads by arity, no properties.
- What a script can import is what jep's `ClassList` calls a package. It reads `java.class.path` and enumerates
  what that names, so a mod whose classes reach the JVM through a loader of its own imports nothing until an
  enquirer says its packages exist; such an enquirer is the next step for those mods, and it delegates.

## Alternatives considered

- **Patch `java_import_hook.py`.** The hook's class loader and enquirer are its two arguments, and it hardwires
  neither; the correction is the thing jep calls configuration.
- **Replace the enquirer with one built from the corpus.** That is how a package jep has never seen gets imported,
  and it needs the delegation above. Measured cost of forgetting it: with an enquirer that answers only for its own
  package, `from java.util import ArrayList` ends in `ModuleNotFoundError: No module named 'java'`.
- **A loader per interpreter.** `SharedInterpreter` carries one config for the process, and the mod runs one
  interpreter (ADR 0009).
- **One more class in `herecraft.api._setup` per need.** That is what the trap asked for, and it costs a Java change
  per type. The api keeps wrapping what a unit works with, and the import is the cheaper door to the rest.
