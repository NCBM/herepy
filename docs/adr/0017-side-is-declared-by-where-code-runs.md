# 17. Side is declared by where code runs, and a unit keeps its identity across incarnations

**Status**: proposed, 2026-11-16.

## Context

One class separates by side: a `@Mod` class carries `dist = Dist.CLIENT` and an `@EventBusSubscriber` carries
`value = Dist.CLIENT`, so a dedicated server never loads it. Everywhere else the repository is side-blind:

- `EventBridge.eventType` calls `Class.forName` with no side check, and reports a miss with "No such event class".
- The wrappers in `herecraft/api/events/` carry no side, and work because nothing has subscribed to one on a server
  that lacks the class.
- `herecraft/api/` names no client-only type, which keeps the Python surface server-safe.
- Python has no way to ask which distribution it is running in.

The shape of the mistake is familiar from Python itself. `if __name__ == "__main__"` answers a three-valued
question with a boolean: under `spawn` the same file runs again with `__name__ == "__mp_main__"`, and a guard
written for two states silently repeats its module level in the child. Three lessons follow — a boolean cannot
carry it, the third value appears on the platform tested last, and the name had to change because the name was the
identity. The first two apply here; the third is what this record declines.

## Decision

- **Side is an injected, closed value.** `HerePy` fills `herecraft.env.dist` from `FMLEnvironment.dist` before
  discovery, and `herecraft` converts it at that seam into an enum of its own, so a unit reads Python source with
  a type. A name the mod does not know is refused.
- **The two questions have two names.** `env.dist` answers "which distribution is this" and holds for the
  process; `level.is_client_side` answers "which side is this code on" and changes.
- **Side follows execution.** A unit's module level stays side-neutral, and work for one side lives in a function
  body marked for it; the loader calls the markers whose side is current. A manifest field would be a claim about
  a whole unit that the loader trusts and skips on, and the class it names would turn up missing on the machine
  that lacks it. A function body simply does not run.
- **A client-only part of the surface is a module whose import resolves nothing.** A client half sits beside its
  common half and keeps each client class behind a function or a name looked up on use. For `herecraft` itself
  review covers this, because there are few such modules; for a unit, the convention below does.
- **The gate belongs to the library, and a unit supplies functions.** `herecraft` decides which marker runs, on
  which distribution, and when; a unit that marks a function `@on_client` states that it has client work and
  nothing about when that work is allowed. Singleplayer forces this: a `CLIENT` distribution that holds a logical
  server makes "is this the server" unanswerable from `dist`. `env.dist` stays readable for messages and
  diagnostics, and it stays out of every `if` that decides what runs.
- **A marker is a name the author imports.** `@on_client` records its function against the unit that is loading,
  the same `current()` and context an `@event` handler uses. A misspelled marker is a `NameError` on the line that
  made it. This is also the rule for every value that crosses from Java: it converts at the seam into a
  Python-owned type, or it comes with a committed stub.
- **A client class is imported inside the function that uses it.** That convention has no check behind it. It buys
  a `setup_client`-shaped function that costs nothing to define on a server, and it costs a module-level
  `from herecraft.api.client import …` becoming a load failure on a dedicated server.
- **An event's side is an attribute on its wrapper.** `EventBridge` receives a class name and decides whether to
  listen before any Python runs, and it is the one place that can turn "a client event on a dedicated server" into
  a sentence. Each wrapper declares its side beside its Java class name, and `__init_subclass__` refuses one that
  names a class without saying.
- **Identity survives the incarnation.** A reload revokes the previous incarnation, compiles the same source again,
  and enables it under the same id; a counter changes, the key does not. `__mp_main__` had to rename itself
  because the name was the identity, and 0003 moved identity into the manifest.
- **The scope releases what the kernel can see.** A unit that starts a thread, opens a descriptor, registers an
  `atexit` hook, writes `sys.modules` or appends to `sys.path` while its module level runs leaves that behind, and
  a reload reports the thread and descriptor counts it did not get back, with the unit's id.
- **Stage is a separate axis, recorded elsewhere.** Startup (before the registries freeze, so "restart to take
  effect") and reloadable are two promises, and the lifecycle markers are the place they first meet.

## Consequences

- A unit on the wrong side is diagnosed as such instead of as a missing name or an `AttributeError` in a tick.
- The manifest carries no `side`, so a unit with one client part stays one unit and the version matrix keeps three
  fields.
- Every event wrapper declares its side, and one that does not fails as the class is defined.
- The module-level convention and the import convention carry no check; `./gradlew runServer` is what finds a
  violation, and that target has never had a Python case run against it.
- A client-only script loads on a dedicated server and idles there, so one file tree shipped to both sides rests
  on the convention rather than on a directory.
- The entry markers belong to the `api` version, because they are the whole of a unit's interface to the loader.
- A reload that leaks a thread says so with a name, which beats a tick handler reporting it three reloads later.
- Refusing an unknown `dist` makes a third distribution loud. `runData` runs under a `dist` too, and is the first
  place to check that the enumeration is complete.

## Alternatives considered

- **A `side` field in the manifest.** It buys a skip before the import, and it costs an all-or-nothing grain per
  unit, a claim nothing can check, and a second answer for the script track, which has no manifest.
- **A fixed function name the loader looks for.** It needs no import, hides the interface from the editor, and
  turns a misspelling into a function that never runs, silently.
- **Assigning the entry to a module variable.** It removes the function-name dependency and stays silent in the
  case that matters: a misspelled variable is an entry that does not exist, where a misspelled marker is a
  `NameError` in the file.
- **A directory or a filename suffix naming the side.** It is the one way to skip a unit before executing it, which
  matters for one pack shipped to both sides; it costs uniformity, and a suffix also changes a script's identity.
- **An injected global with a hand-written stub.** `herecraft` ships its own source, so a stub beside it is a
  second description to drift from; converting at the seam gives the type for free.
- **A boolean `env.is_client`.** The `__name__ == "__main__"` mistake: right on the distribution that is tested and
  wrong on the other one, in the branch that does nothing visible.
- **Inferring side from the Java class name.** `net.neoforged.neoforge.client.…` encodes it today, and a wrapper
  whose name says nothing, or says it wrongly, has nowhere to correct the guess.
- **Per-side artifacts, or per-side source sets as Forge 1.12 had.** The most honest separation, at two artifacts,
  two version lines, and a rule about what may cross.
- **A guard the author writes.** `if env.dist is CLIENT:` is the function body with worse visibility, it fails
  open, and it puts policy in every unit.
- **Letting a unit decide its own timing.** It reads as flexibility, and it leaves the loader unable to answer
  "what runs on a dedicated server" without asking every unit.
- **Classifying a script by scanning its syntax.** A file classified by its module-level imports guesses at intent
  and refuses the script whose client work sits inside a function.
- **A static check of module-level side effects with `ast`.** The rule list is guesswork (`open` to read is fine,
  `threading` is sometimes the point), it duplicates `ruff`, and it sees module-level statements while the leak
  arrives through a call. The reload count names the same leak with less policy.
- **Reload as a fresh unit with a new id.** The registry would hold two entries per file, every registration would
  look like a conflict, and "the same script, again" would not survive the changing key.
