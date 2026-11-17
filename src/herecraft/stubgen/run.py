"""herecraft.stubgen.run — one run of the generator: the seeds it is given, written where it is told.

A run is what a caller asks for (ADR 0021): the classes those seeds reach, reflected, rendered a module at a time,
pruned to what this run decided, and reported beside the corpus. The trigger is the caller's — a command in a dev
client, a script pack entry — so nothing here decides where the seeds or the output come from.
"""

from __future__ import annotations

from collections.abc import Iterable
import json
from logging import getLogger
from pathlib import Path
from typing import Any

from .core import StubGenerator, StubReport
from .overlay import Overlay

logger = getLogger("herecraft.stubgen.run")

REPORT = "stubgen-report.json"


def write(
    seeds: Iterable[str],
    output: str | Path,
    *,
    data: str | Path | None = None,
    wrapper: type[Any] | None = None,
    classloader: Any = None,
) -> tuple[StubReport, int]:
    """Write the corpus for `seeds` to `output`, with its report, and answer what the run did and what it pruned.

    `data` is the name data the class files do not carry — parameter names and docstrings — and a run without it
    writes `argN` and no docstrings. `wrapper` and `classloader` are what reflection reaches through; both default
    to the game's.
    """
    target = Path(output)
    overlay = None
    if data is not None:
        source = Path(data)
        if source.is_file():
            overlay = Overlay.load(source)
        else:
            logger.warning("%s is not there: stubs keep argN and no docstrings", source)
    else:
        logger.info("no name data: stubs keep argN and no docstrings")
    generator = StubGenerator(target, wrapper=wrapper, classloader=classloader, overlay=overlay)
    report = generator.generate_surface(seeds)
    pruned = generator.prune()
    target.mkdir(parents=True, exist_ok=True)
    _ = (target / REPORT).write_text(json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8")
    return report, pruned
