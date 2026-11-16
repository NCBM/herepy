"""herecraft.stubgen.classpath — Enumerate classes from JAR files."""

from __future__ import annotations

import contextlib
from logging import getLogger
from pathlib import Path

from java.io import File
from java.util.jar import JarFile

logger = getLogger("herecraft.stubgen.classpath")


def get_jar_classes(*jarfiles: str | Path) -> set[str]:
    """Get all class names from JAR files (dotted format)."""
    result: set[str] = set()
    for jarfile in jarfiles:
        try:
            logger.info("Processing: %r", jarfile)
            with contextlib.closing(JarFile(File(str(jarfile)))) as jar:
                for entry in jar.entries().asIterator():
                    name: str = entry.getName()
                    if name.endswith(".class"):
                        result.add(name.removesuffix(".class").replace("/", "."))
        except Exception:
            logger.exception("Failed to process JAR: %s", jarfile)
    return result
