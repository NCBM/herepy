from __future__ import annotations

from typing import ClassVar

from herecraft.api.core import BlockPos
from herecraft.api.entities import Player
from herecraft.api.world import BlockState

from ._base import Event, Side


class BlockBreakEvent(Event):
    """Wraps net.neoforged.neoforge.event.level.BlockEvent$BreakEvent."""

    __java_class_name__: ClassVar[str] = "net.neoforged.neoforge.event.level.BlockEvent$BreakEvent"
    __side__: ClassVar[Side] = Side.BOTH

    @property
    def pos(self) -> BlockPos:
        return BlockPos(self._jobj.getPos())

    @property
    def state(self) -> BlockState:
        return BlockState(self._jobj.getState())

    @property
    def player(self) -> Player:
        return Player(self._jobj.getPlayer())

    @property
    def exp_to_drop(self) -> int:
        return int(self._jobj.getExpToDrop())

    @exp_to_drop.setter
    def exp_to_drop(self, value: int) -> None:
        self._jobj.setExpToDrop(value)


class BlockPlaceEvent(Event):
    """Wraps net.neoforged.neoforge.event.level.BlockEvent$EntityPlaceEvent."""

    __java_class_name__: ClassVar[str] = "net.neoforged.neoforge.event.level.BlockEvent$EntityPlaceEvent"
    __side__: ClassVar[Side] = Side.BOTH

    @property
    def pos(self) -> BlockPos:
        return BlockPos(self._jobj.getPos())

    @property
    def placed_block(self) -> BlockState:
        return BlockState(self._jobj.getPlacedBlock())

    @property
    def replaced_block(self) -> BlockState:
        return BlockState(self._jobj.getBlockSnapshot().getReplacedBlock())

    @property
    def player(self) -> Player | None:
        entity = self._jobj.getEntity()
        if entity is None:
            return None
        return Player(entity)
