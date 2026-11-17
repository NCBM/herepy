"""The stub corpus generator, on demand (ADR 0021).

`herecraft.stubgen` is the work: it reflects the classes the surface declares, renders them a module at a time and
reports what it decided. This unit is the trigger a running game offers, and what it decides is where a run keeps
its output and where it looks for the name data.

The name data is the game's, and only the game's: a mapping set covers Minecraft and NeoForge, and nothing covers a
mod's own classes. A run without it still writes the corpus — `argN` for a parameter whose class file carries no
name, and no docstring — so a tree that never produced the data loses the names and keeps the stubs.
`HEREPY_STUBGEN_DATA` names the file when there is one; this repository's dev runs export the build's projection at
it, and `HEREPY_STUBGEN_OUTPUT` moves where a run writes.

`/stubgen write` is measured in minutes on a client, so it answers when it is done rather than while it runs.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from herecraft import env
from herecraft.api.core import Component
from herecraft.commands import command
from herecraft.stubgen import declared_seeds, write

logger = logging.getLogger("herecraft.stubgen.unit")

OUTPUT = os.environ.get("HEREPY_STUBGEN_OUTPUT", "python/typings")
DATA = os.environ.get("HEREPY_STUBGEN_DATA", "")


def _path(configured: str) -> Path:
    """The configured path, read against the game directory unless it is absolute."""
    path = Path(configured)
    return path if path.is_absolute() else env.game_dir / path


@command("stubgen write")
async def _write_command(source: Any) -> None:
    """`/stubgen write`: the corpus for the names the surface declares, and the report that says what it did."""
    output = _path(OUTPUT)
    logger.info("stubgen: writing the corpus to %s", output)
    report, pruned = write(declared_seeds(), output, data=_path(DATA) if DATA else None)
    answer = (
        f"{report.count('written')} written, {report.count('rejected')} rejected, "
        f"{report.count('failed')} failed, {pruned} pruned -> {output}"
    )
    logger.info("stubgen: %s", answer)
    source.sendSystemMessage(Component.literal(answer).java)
