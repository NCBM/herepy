# Vendored third-party code

| Package | Source | Release | Commit | Files |
| --- | --- | --- | --- | --- |
| `composat` | `../composat` (https://github.com/NCBM/composat) | 1.0.2 | `b0f2a03` | `src/composat/scope.py` |

`composat/scope.py` is copied byte for byte. Its SHA-256 is recorded here so a difference shows up as
a difference, not as a bug report against this project:

```
ed685e24b84f7e6e6dce370b42a838815205a10608b245006eac291b8b1cc0d3  src/herecraft/_vendor/composat/scope.py
```

`composat/__init__.py` is not upstream's: it names the layers this project adopts (ADR 0010 — the
effect scope, and nothing above it), so the vendored package cannot be mistaken for all of `composat`.

## Why a copy rather than a dependency

`composat` 1.0.2 declares `typing-extensions>=4.16.0`. The runtime now carries
`typing_extensions==4.16.0` as a base dependency, so that is satisfied — but installing `composat`
itself would still need a build backend (it is built with `pdm-backend`) and an index to reach, and
neither is something a player's runtime can be relied on to have. ADR 0010 refuses an unpinned
`pip install` for the same reason: this project adopts one layer of `composat`, not the package, and
`scope.py` imports only the standard library, so the copy costs one file.

A runtime manifest that pins wheels properly would replace this directory — `composat` would arrive
as a pinned wheel like everything else, and `typing_extensions` is no longer the obstacle to that.
Until then the file here is the pin.

## Moving it forward

Copy the new upstream file over this one, re-record the version, commit, and checksum. Do not edit
the copy: a local change to vendored code is a change that the next copy silently reverts.
