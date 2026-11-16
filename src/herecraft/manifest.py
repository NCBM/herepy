"""herecraft.manifest — what a packaged unit says about itself (ADR 0003).

A manifest carries a unit's identity: an id, a version, the `api` series it was written against, and what it needs.
It is read before anything is imported, which turns an `api` mismatch into a sentence about two files.

The entry is the package's own `__init__.py`, the rule the script track follows too (ADR 0018), so no field names
it and no unit points at a module outside its root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any
import zipfile

from herecraft import __api__

MANIFEST_NAME = "manifest.toml"

#: The prefix every unit's import name starts with, so a unit cannot shadow a module or another unit.
MODULE_PREFIX = "herecraft_unit_"


class ManifestError(Exception):
    """A manifest that cannot be read, or that says something the loader will not accept."""


@dataclass(frozen=True, slots=True)
class Manifest:
    """What a unit declares about itself."""

    id: str
    version: str
    api: tuple[str, ...]
    dependencies: tuple[str, ...] = ()

    @property
    def namespace(self) -> str:
        """The part of the id before the slash: who published it."""
        return self.id.split("/", 1)[0]

    @property
    def name(self) -> str:
        """The part of the id after the slash: what it is called within that namespace."""
        return self.id.split("/", 1)[1]

    @property
    def module_name(self) -> str:
        """The name this unit is imported under, derived from its id and not from where it sits."""
        flat = self.id.replace("/", "_").replace("-", "_").replace(".", "_")
        return MODULE_PREFIX + flat.lower()

    def check_api(self, current: str = __api__) -> None:
        """Refuse a unit written for an `api` series this runtime does not offer, and say both sides."""
        if current in self.api:
            return
        msg = (
            f"unit {self.id} {self.version} was written for herecraft api {' or '.join(self.api)}, and this "
            f"runtime offers {current}: replace the unit, or the runtime, whichever is older"
        )
        raise ManifestError(msg)


def read_directory(root: Path) -> Manifest:
    """Read the manifest of a unit that is a directory."""
    path = root / MANIFEST_NAME
    try:
        data = tomllib.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        msg = f"{root}: cannot read {MANIFEST_NAME}: {error}"
        raise ManifestError(msg) from error
    return _build(data, str(root))


def read_archive(path: Path) -> tuple[Manifest, str]:
    """Read the manifest of a `.pyz`, and answer the name of the directory holding it.

    A loose archive — one whose root *is* the package — cannot be imported by name, so the build wraps the
    unit in a directory that must match the name it derives from its id. The name is checked here rather than
    at import time, where zipimport would fail with a missing file.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            holders = [
                entry.filename[: -len(MANIFEST_NAME) - 1]
                for entry in archive.infolist()
                if entry.filename.endswith("/" + MANIFEST_NAME)
            ]
            if len(holders) != 1:
                msg = (
                    f"{path}: expected one directory holding {MANIFEST_NAME}, found {len(holders)}. A unit is "
                    "wrapped in a directory inside the archive, because an archive whose root is the package "
                    "cannot be imported under a name (ADR 0018)."
                )
                raise ManifestError(msg)
            holder = holders[0]
            with archive.open(f"{holder}/{MANIFEST_NAME}") as handle:
                data = tomllib.loads(handle.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, zipfile.BadZipFile) as error:
        msg = f"{path}: cannot read {MANIFEST_NAME}: {error}"
        raise ManifestError(msg) from error
    manifest = _build(data, str(path))
    if holder != manifest.module_name:
        msg = (
            f"{path}: the directory inside the archive is {holder!r}, and the manifest's id wants "
            f"{manifest.module_name!r}. The two have to agree, because zipimport finds a module by its name."
        )
        raise ManifestError(msg)
    return manifest, holder


def _build(data: dict[str, Any], origin: str) -> Manifest:
    """Turn parsed TOML into a manifest, naming the field that is wrong rather than the file alone."""
    missing = [field for field in ("id", "version", "api") if field not in data]
    if missing:
        msg = f"{origin}: {MANIFEST_NAME} is missing {', '.join(missing)}"
        raise ManifestError(msg)

    unit_id = data["id"]
    if not isinstance(unit_id, str) or unit_id.count("/") != 1:
        msg = f"{origin}: id must be a string of the form <namespace>/<name>, not {unit_id!r}"
        raise ManifestError(msg)
    namespace, name = unit_id.split("/")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-.")
    for part in (namespace, name):
        if not part or set(part.lower()) - allowed:
            msg = f"{origin}: {unit_id!r} may only hold lowercase letters, digits, '_', '-' and '.'"
            raise ManifestError(msg)

    version = data["version"]
    if not isinstance(version, str) or not version:
        msg = f"{origin}: version must be a non-empty string, not {version!r}"
        raise ManifestError(msg)

    api = data["api"]
    if isinstance(api, str):
        series = (api,)
    elif isinstance(api, list) and all(isinstance(item, str) for item in api):
        series = tuple(api)
    else:
        msg = f"{origin}: api must be a string or a list of strings, not {api!r}"
        raise ManifestError(msg)

    dependencies = data.get("dependencies", [])
    if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
        msg = f"{origin}: dependencies must be a list of strings, not {dependencies!r}"
        raise ManifestError(msg)

    return Manifest(id=unit_id, version=version, api=series, dependencies=tuple(dependencies))
