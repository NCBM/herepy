"""Called by HerePy Java during interpreter initialization."""

from __future__ import annotations

__all__ = ["_bootstrap"]

from typing import Any

from ._registry import register_java_class, register_wrapper


def _bootstrap(
    block_pos_class: Any,
    vec3_class: Any,
    resource_location_class: Any,
    component_class: Any,
    item_stack_class: Any,
    level_class: Any,
    server_class: Any,
    entity_class: Any,
    player_class: Any,
) -> None:
    """Inject Java class references and register all wrapper types.

    Called from Java via interpreter.invoke before any wrapper factory
    methods are usable.
    """
    from .core import BlockPos, Component, ResourceLocation, Vec3, _set_java_classes
    from .entities import Entity, LivingEntity, Player
    from .items import ItemStack, _set_item_stack_class
    from .world import BlockState, Level, Server

    # Inject Java classes for factory classmethods
    register_java_class("net.minecraft.core.BlockPos", block_pos_class)
    register_java_class("net.minecraft.world.phys.Vec3", vec3_class)
    register_java_class("net.minecraft.resources.ResourceLocation", resource_location_class)
    register_java_class("net.minecraft.network.chat.Component", component_class)
    register_java_class("net.minecraft.world.item.ItemStack", item_stack_class)
    register_java_class("net.minecraft.world.level.Level", level_class)
    register_java_class("net.minecraft.server.MinecraftServer", server_class)
    register_java_class("net.minecraft.world.entity.Entity", entity_class)
    register_java_class("net.minecraft.world.entity.player.Player", player_class)

    # Set sentinel vars via dedicated setters (avoids cross-module private access)
    _set_java_classes(block_pos_class, vec3_class, resource_location_class, component_class)
    _set_item_stack_class(item_stack_class)

    # Register wrapper types for wrap() auto-wrapping
    register_wrapper("net.minecraft.core.BlockPos", BlockPos)
    register_wrapper("net.minecraft.world.phys.Vec3", Vec3)
    register_wrapper("net.minecraft.resources.ResourceLocation", ResourceLocation)
    register_wrapper("net.minecraft.network.chat.Component", Component)
    register_wrapper("net.minecraft.world.item.ItemStack", ItemStack)
    register_wrapper("net.minecraft.world.level.Level", Level)
    register_wrapper("net.minecraft.world.level.block.state.BlockState", BlockState)
    register_wrapper("net.minecraft.server.MinecraftServer", Server)
    register_wrapper("net.minecraft.world.entity.Entity", Entity)
    register_wrapper("net.minecraft.world.entity.LivingEntity", LivingEntity)
    register_wrapper("net.minecraft.world.entity.player.Player", Player)
    register_wrapper("net.minecraft.server.level.ServerPlayer", Player)

    # Register event wrappers
    from .events._setup import _register_event_wrappers

    _register_event_wrappers()
