from __future__ import annotations

from typing import Any

from ._base import JavaWrapper
from .core import Component, ResourceLocation

# Sentinel — set via _set_item_stack_class() at startup
_ItemStackClass: Any = None


def _set_item_stack_class(cls: Any) -> None:
    global _ItemStackClass
    _ItemStackClass = cls


class ItemStack(JavaWrapper[Any]):
    """Stack of items with count and data. Wraps net.minecraft.world.item.ItemStack."""

    @property
    def item(self) -> ResourceLocation:
        return ResourceLocation(self._jobj.getItem().builtInRegistryHolder().key().location())

    @property
    def count(self) -> int:
        return int(self._jobj.getCount())

    @count.setter
    def count(self, value: int) -> None:
        self._jobj.setCount(value)

    @property
    def is_empty(self) -> bool:
        return bool(self._jobj.isEmpty())

    @property
    def max_stack_size(self) -> int:
        return int(self._jobj.getMaxStackSize())

    @property
    def display_name(self) -> Component:
        return Component(self._jobj.getDisplayName())

    @property
    def is_damageable(self) -> bool:
        return bool(self._jobj.isDamageable())

    @property
    def damage(self) -> int:
        return int(self._jobj.getDamageValue())

    @damage.setter
    def damage(self, value: int) -> None:
        self._jobj.setDamageValue(value)

    @property
    def max_damage(self) -> int:
        return int(self._jobj.getMaxDamage())

    def copy(self) -> ItemStack:
        return ItemStack(self._jobj.copy())

    def split(self, amount: int) -> ItemStack:
        """Split off `amount` items; returns the split-off stack."""
        return ItemStack(self._jobj.split(amount))

    def is_same_item(self, other: ItemStack) -> bool:
        """Whether the two stacks hold the same item, which is the question `ItemStack.isSameItem` asks."""
        return self.item == other.item

    @classmethod
    def empty(cls) -> ItemStack:
        return cls(_ItemStackClass.EMPTY)
