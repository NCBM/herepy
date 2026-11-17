from __future__ import annotations

from typing import ClassVar

from herecraft.api.entities import Entity, LivingEntity
from herecraft.api.world import Level

from ._base import Event, Side


class LivingDeathEvent(Event):
    """Wraps net.neoforged.neoforge.event.entity.living.LivingDeathEvent."""

    __java_class_name__: ClassVar[str] = "net.neoforged.neoforge.event.entity.living.LivingDeathEvent"
    __side__: ClassVar[Side] = Side.BOTH

    @property
    def entity(self) -> LivingEntity:
        return LivingEntity(self._jobj.getEntity())

    @property
    def source_entity(self) -> Entity | None:
        src = self._jobj.getSource().getEntity()
        if src is None:
            return None
        return Entity(src)


class LivingDamageEvent(Event):
    """Wraps net.neoforged.neoforge.event.entity.living.LivingDamageEvent$Pre.

    NeoForge splits damage into a phase before it lands and one after, so `Pre` is the cancellable one and the
    only one whose amount can still be set.
    """

    __java_class_name__: ClassVar[str] = "net.neoforged.neoforge.event.entity.living.LivingDamageEvent$Pre"
    __side__: ClassVar[Side] = Side.BOTH

    @property
    def entity(self) -> LivingEntity:
        return LivingEntity(self._jobj.getEntity())

    @property
    def amount(self) -> float:
        return float(self._jobj.getNewDamage())

    @amount.setter
    def amount(self, value: float) -> None:
        self._jobj.setNewDamage(value)

    @property
    def source_entity(self) -> Entity | None:
        src = self._jobj.getSource().getEntity()
        if src is None:
            return None
        return Entity(src)


class EntityJoinLevelEvent(Event):
    """Wraps net.neoforged.neoforge.event.entity.EntityJoinLevelEvent."""

    __java_class_name__: ClassVar[str] = "net.neoforged.neoforge.event.entity.EntityJoinLevelEvent"
    __side__: ClassVar[Side] = Side.BOTH

    @property
    def entity(self) -> Entity:
        return Entity(self._jobj.getEntity())

    @property
    def level(self) -> Level:
        return Level(self._jobj.getLevel())
