from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._base import JavaWrapper
from .core import BlockPos, Component, ResourceLocation, Vec3

if TYPE_CHECKING:
    from .items import ItemStack
    from .world import Level


class Entity(JavaWrapper[Any]):
    """Base entity. Wraps net.minecraft.world.entity.Entity."""

    @property
    def uuid(self) -> str:
        return str(self._jobj.getUUID().toString())

    @property
    def entity_type(self) -> ResourceLocation:
        return ResourceLocation(self._jobj.getType().builtInRegistryHolder().key().location())

    @property
    def position(self) -> Vec3:
        return Vec3(self._jobj.position())

    @property
    def block_pos(self) -> BlockPos:
        return BlockPos(self._jobj.blockPosition())

    @property
    def x(self) -> float:
        return float(self._jobj.getX())

    @property
    def y(self) -> float:
        return float(self._jobj.getY())

    @property
    def z(self) -> float:
        return float(self._jobj.getZ())

    @property
    def yaw(self) -> float:
        return float(self._jobj.getYRot())

    @property
    def pitch(self) -> float:
        return float(self._jobj.getXRot())

    @property
    def velocity(self) -> Vec3:
        return Vec3(self._jobj.getDeltaMovement())

    @velocity.setter
    def velocity(self, v: Vec3) -> None:
        self._jobj.setDeltaMovement(v._jobj)

    @property
    def is_on_ground(self) -> bool:
        return bool(self._jobj.onGround())

    @property
    def is_alive(self) -> bool:
        return bool(self._jobj.isAlive())

    @property
    def display_name(self) -> Component:
        return Component(self._jobj.getDisplayName())

    @property
    def name(self) -> str:
        return str(self._jobj.getName().getString())

    @property
    def level(self) -> Level:
        from .world import Level

        return Level(self._jobj.level())

    def teleport(self, x: float, y: float, z: float) -> None:
        self._jobj.teleportTo(x, y, z)

    def add_tag(self, tag: str) -> None:
        self._jobj.addTag(tag)

    def has_tag(self, tag: str) -> bool:
        return bool(self._jobj.getTags().contains(tag))

    def get_tags(self) -> set[str]:
        result: set[str] = set()
        it = self._jobj.getTags().iterator()
        while it.hasNext():
            result.add(str(it.next()))
        return result


class LivingEntity(Entity):
    """Entity with health and effects. Wraps net.minecraft.world.entity.LivingEntity."""

    @property
    def health(self) -> float:
        return float(self._jobj.getHealth())

    @health.setter
    def health(self, value: float) -> None:
        self._jobj.setHealth(value)

    @property
    def max_health(self) -> float:
        return float(self._jobj.getMaxHealth())

    @property
    def armor(self) -> int:
        return int(self._jobj.getArmorValue())

    @property
    def is_dead(self) -> bool:
        return bool(self._jobj.isDeadOrDying())

    def heal(self, amount: float) -> None:
        self._jobj.heal(amount)

    def hurt(self, amount: float) -> None:
        """Deal generic damage. For specific DamageSource, use .java.hurt(source, amount)."""
        self._jobj.hurt(self._jobj.level().damageSources().generic(), amount)


class Player(LivingEntity):
    """Human player. Wraps net.minecraft.world.entity.player.Player."""

    @property
    def username(self) -> str:
        return str(self._jobj.getGameProfile().getName())

    @property
    def game_profile_id(self) -> str:
        return str(self._jobj.getGameProfile().getId().toString())

    @property
    def inventory(self) -> PlayerInventory:
        return PlayerInventory(self._jobj.getInventory())

    @property
    def held_item(self) -> ItemStack:
        from .items import ItemStack

        return ItemStack(self._jobj.getMainHandItem())

    @property
    def offhand_item(self) -> ItemStack:
        from .items import ItemStack

        return ItemStack(self._jobj.getOffhandItem())

    @property
    def food_level(self) -> int:
        return int(self._jobj.getFoodData().getFoodLevel())

    @property
    def saturation(self) -> float:
        return float(self._jobj.getFoodData().getSaturationLevel())

    @property
    def experience_level(self) -> int:
        return int(self._jobj.experienceLevel)

    @property
    def xp_progress(self) -> float:
        return float(self._jobj.experienceProgress)

    @property
    def is_creative(self) -> bool:
        return bool(self._jobj.isCreative())

    @property
    def is_spectator(self) -> bool:
        return bool(self._jobj.isSpectator())

    def send_message(self, text: str | Component) -> None:
        msg = Component.literal(text) if isinstance(text, str) else text
        self._jobj.sendSystemMessage(msg._jobj)


class PlayerInventory(JavaWrapper[Any]):
    """Wraps net.minecraft.world.entity.player.Inventory."""

    @property
    def selected_slot(self) -> int:
        return int(self._jobj.selected)

    def get_item(self, slot: int) -> ItemStack:
        from .items import ItemStack

        return ItemStack(self._jobj.getItem(slot))

    def set_item(self, slot: int, stack: Any) -> None:
        jobj = stack._jobj if isinstance(stack, JavaWrapper) else stack
        self._jobj.setItem(slot, jobj)

    def __len__(self) -> int:
        return int(self._jobj.getContainerSize())
