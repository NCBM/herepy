# 3. A unit is identified by a manifest, not by the module name it loads as

**Status**: accepted, 2026-11-16.

## Context

`herecraft/herepy-shims.py` decides what a unit *is* from where its folder sits:

```python
sys.path.insert(0, "python/scripts")
for mod in os.listdir("python/scripts"):
    importlib.import_module(mod)          # the module name is the folder name
```

Three things follow, and all three are already true of the code:

- **A folder name is an import statement.** A unit called `json/`, `types/` or `herecraft/` shadows the
  standard library — for every unit, permanently, because the insert goes to the front of `sys.path`.
- **A folder name is the identity.** Renaming a directory is a breaking change to every `import` any
  other unit writes, and it cannot be caught: the identity exists nowhere but the filesystem.
- **A unit has no metadata.** No id, no version, no author, and — the one that costs most — no
  statement of which `herecraft` API it was written against.

## Decision

A unit's identity is a manifest's, and the name it loads as is derived from that identity.

- **Identity**: `<namespace>/<name>`, declared in the unit's manifest.
- **Entry**: the package's own `__init__.py`, which keeps the entry and the root in one place and gives the field
  nothing to disagree with.
- **Import name**: derived (`herecraft_unit_<flattened identity>`), taken from the identity and never from the file
  system. It is a plain top-level name, because a parent package would exist only to exist (0018).
- **Metadata**: `version`, `api` (a compatibility series the kernel checks) and `dependencies`.
- **One place per collision**: packaged units and the script pack all land in the discovery of one source, and the
  script pack's identity is fixed at `local/scripts`, so a clash shows up as two candidates for one name rather than
  as a silent second copy.

## Consequences

- Folder names stop being load-bearing: a unit can be moved or renamed without touching an `import`.
- Shadowing the standard library stops being possible.
- The `api` range makes an incompatible unit a startup failure with a name in it, rather than an
  `AttributeError` in a tick.
- `dependencies` becomes a load-order input among packaged units, not decoration. The script track needs none: the
  unit that owns a script pack loads it (0018).
- A unit that has never been given a version (an ad-hoc script) carries a default rather than an exemption, so
  "which version is this" always has an answer.

## Alternatives considered

- **Keep the directory name as the identity.** Free now, and it is encoded in every line of user code
  the moment someone writes a unit — the most expensive thing to change later, which is why this is
  decided before there is user code.
- **Python packaging conventions**: a `pyproject.toml` and an entry point. A wheel-shaped identity
  drags in dependency resolution and an installer, neither of which the embedded runtime has (it ships
  a bare CPython with `pip` and `jep`, and no numpy).
- **Minecraft's own resource-id convention** (`modid:path`). Superficially attractive, since units will
  register items and blocks under a namespace; but Python units are not resources, and one identifier
  serving both invites confusing a unit with something it registered.
- **Hashing the content for identity.** Answers "which version of this unit" — which is what the
  fingerprint in ADR 0010 is for — and answers the wrong question here, where the need is a stable name
  across edits.
