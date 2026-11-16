"""herecraft.kernel.loader — the one source, and what discovery turns into loaded units (ADR 0018).

The kernel ships one source: `<game directory>/mods`, where a unit is a `.pyz` or a directory, and either way a
package with a manifest at its root. Whoever discovers a unit holds it, and the kernel offers the verbs to load and
enable one.

A unit is imported (ADR 0018), and its package name comes from its id, so a folder name stays out of the import
system.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import importlib.machinery
import importlib.util
import logging
from pathlib import Path
import sys
import zipimport

from herecraft import env, event, markers
from herecraft.kernel.unit import UnitContext, active
from herecraft.manifest import MANIFEST_NAME, Manifest, ManifestError, read_archive, read_directory

logger = logging.getLogger("herecraft.kernel")

#: The suffixes a packaged unit may have. Everything else in `mods/` belongs to the Java loader.
ARCHIVE_SUFFIXES = (".pyz", ".pyzw")


@dataclass(frozen=True, slots=True)
class UnitSource:
    """One candidate: where it is, what it says about itself, and whether it arrived as an archive."""

    path: Path
    manifest: Manifest
    archive: bool

    @property
    def module_name(self) -> str:
        """The name this unit is imported under."""
        return self.manifest.module_name


@dataclass(frozen=True, slots=True)
class Loaded:
    """A unit that ran: the source it came from and the context its registrations belong to."""

    source: UnitSource
    unit: UnitContext


def discover(mods_dir: Path) -> list[UnitSource]:
    """Answer the units under ``mods_dir``, sorted by id so two runs load the same order.

    A manifest that cannot be read is reported and skipped rather than thrown: one broken unit is one broken
    unit, and the rest of the directory still loads.
    """
    if not mods_dir.is_dir():
        return []
    found: list[UnitSource] = []
    for entry in sorted(mods_dir.iterdir()):
        try:
            if entry.is_dir():
                if not (entry / MANIFEST_NAME).is_file():
                    logger.debug("%s holds no %s, so it is not a unit", entry, MANIFEST_NAME)
                    continue
                found.append(UnitSource(entry, read_directory(entry), archive=False))
            elif entry.suffix.lower() in ARCHIVE_SUFFIXES:
                manifest, _holder = read_archive(entry)
                found.append(UnitSource(entry, manifest, archive=True))
        except ManifestError as error:
            logger.error("skipping %s: %s", entry, error)
    return sorted(found, key=lambda source: source.manifest.id)


def load(source: UnitSource) -> Loaded:
    """Import one unit inside its own context, and answer what it registered.

    The `api` check happens before the import: a unit written for another series never gets to run, so a
    mismatch cannot look like a bug in the unit.
    """
    source.manifest.check_api()
    spec = _specification(source)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        msg = f"{source.path}: has no loader, so it cannot be imported"
        raise ManifestError(msg)
    sys.modules[spec.name] = module
    with active(source.manifest.id) as unit:
        try:
            spec.loader.exec_module(module)
            # A distribution marker runs here, inside the unit's own context: what it registers belongs to the
            # unit and is staged like everything else, so enabling is still the only step that reaches the bus.
            if env.current().has_client:
                for hook in unit.hooks(markers.CLIENT):
                    _ = hook()
        except BaseException:
            # A unit that failed half-way leaves a module in the cache that nothing owns; drop it so the next
            # attempt (a reload, or a fixed file) starts from nothing rather than from a ghost.
            _ = sys.modules.pop(spec.name, None)
            raise
    return Loaded(source, unit)


def enable(loaded: Loaded) -> None:
    """Let a unit's registrations reach the bus, in the order the unit made them (ADR 0004)."""
    loaded.unit.enable()


async def replace(old: UnitContext, load: Callable[[], UnitContext]) -> UnitContext:
    """Put a new incarnation of ``old`` in place, keeping every listener on the bus throughout (ADR 0018).

    The order is the whole point: the old handlers leave the dispatch table synchronously, the new incarnation loads
    and enables, and the old scope is released last — so an event class that had one listener keeps one. What the
    unit misses is what arrives while its own load runs, which is why this is not a hot swap.
    """
    detached = event.detach(old.name)
    logger.debug("%s: %d handlers left the dispatch table", old.name, detached)
    fresh = load()
    fresh.enable()
    await old.revoke_all()
    return fresh


def _specification(source: UnitSource) -> importlib.machinery.ModuleSpec:
    """The import machinery's view of one unit: a package rooted where the unit lives."""
    if source.archive:
        importer = zipimport.zipimporter(str(source.path))
        spec = importer.find_spec(source.module_name)
        if spec is None or spec.loader is None:
            msg = f"{source.path}: the archive holds no {source.module_name!r} package, so nothing can import it"
            raise ManifestError(msg)
        return spec

    entry = source.path / "__init__.py"
    if not entry.is_file():
        msg = f"{source.path}: a unit directory needs an __init__.py, which is its entry (ADR 0018)"
        raise ManifestError(msg)
    spec = importlib.util.spec_from_file_location(
        source.module_name, entry, submodule_search_locations=[str(source.path)]
    )
    if spec is None:
        msg = f"{entry}: importlib could not build a specification for it"
        raise ManifestError(msg)
    return spec
