"""herecraft.api — Pythonic wrappers for Minecraft/NeoForge types.

Usage::

    from herecraft.api import Player, Level, BlockPos, ItemStack, Server
    from herecraft.api import wrap  # auto-wrap JEP proxies
"""

from ._registry import wrap
from .core import BlockPos, Component, ResourceLocation, Vec3
from .entities import Entity, LivingEntity, Player, PlayerInventory
from .items import ItemStack
from .world import BlockState, Level, Server

__all__ = [
    "BlockPos",
    "BlockState",
    "Component",
    "Entity",
    "ItemStack",
    "Level",
    "LivingEntity",
    "Player",
    "PlayerInventory",
    "ResourceLocation",
    "Server",
    "Vec3",
    "wrap",
]
