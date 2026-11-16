from __future__ import annotations

from typing import ClassVar

from herecraft.api.core import ResourceLocation
from herecraft.api.entities import Entity, Player

from ._base import Event, Side


class PlayerEvent(Event):
    """Base for player-related events."""

    @property
    def player(self) -> Player:
        return Player(self._jobj.getEntity())


class PlayerLoggedInEvent(PlayerEvent):
    """Wraps net.neoforged.neoforge.event.entity.player.PlayerEvent$PlayerLoggedInEvent."""

    __java_class_name__: ClassVar[str] = "net.neoforged.neoforge.event.entity.player.PlayerEvent$PlayerLoggedInEvent"
    __side__: ClassVar[Side] = Side.BOTH


class PlayerLoggedOutEvent(PlayerEvent):
    """Wraps net.neoforged.neoforge.event.entity.player.PlayerEvent$PlayerLoggedOutEvent."""

    __java_class_name__: ClassVar[str] = "net.neoforged.neoforge.event.entity.player.PlayerEvent$PlayerLoggedOutEvent"
    __side__: ClassVar[Side] = Side.BOTH


class PlayerRespawnEvent(PlayerEvent):
    """Wraps net.neoforged.neoforge.event.entity.player.PlayerRespawnEvent."""

    __java_class_name__: ClassVar[str] = "net.neoforged.neoforge.event.entity.player.PlayerRespawnEvent"
    __side__: ClassVar[Side] = Side.BOTH

    @property
    def is_end_conquered(self) -> bool:
        return bool(self._jobj.isEndConquered())


class PlayerChangedDimensionEvent(PlayerEvent):
    """Wraps net.neoforged.neoforge.event.entity.player.PlayerEvent$PlayerChangedDimensionEvent."""

    __java_class_name__: ClassVar[str] = (
        "net.neoforged.neoforge.event.entity.player.PlayerEvent$PlayerChangedDimensionEvent"
    )
    __side__: ClassVar[Side] = Side.BOTH

    @property
    def from_dimension(self) -> ResourceLocation:
        return ResourceLocation(self._jobj.getFrom().location())

    @property
    def to_dimension(self) -> ResourceLocation:
        return ResourceLocation(self._jobj.getTo().location())


class AttackEntityEvent(Event):
    """Wraps net.neoforged.neoforge.event.entity.player.AttackEntityEvent."""

    __java_class_name__: ClassVar[str] = "net.neoforged.neoforge.event.entity.player.AttackEntityEvent"
    __side__: ClassVar[Side] = Side.BOTH

    @property
    def player(self) -> Player:
        return Player(self._jobj.getEntity())

    @property
    def target(self) -> Entity:
        return Entity(self._jobj.getTarget())


class PlayerInteractEvent(Event):
    """Wraps net.neoforged.neoforge.event.entity.player.PlayerInteractEvent."""

    __java_class_name__: ClassVar[str] = "net.neoforged.neoforge.event.entity.player.PlayerInteractEvent"
    __side__: ClassVar[Side] = Side.BOTH

    @property
    def player(self) -> Player:
        return Player(self._jobj.getEntity())
