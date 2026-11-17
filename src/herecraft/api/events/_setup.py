"""Register all event wrappers in the wrapper registry."""

from __future__ import annotations

from herecraft.api._registry import register_wrapper

from .block import BlockBreakEvent, BlockPlaceEvent
from .entity import EntityJoinLevelEvent, LivingDamageEvent, LivingDeathEvent
from .player import (
    AttackEntityEvent,
    PlayerChangedDimensionEvent,
    PlayerInteractEvent,
    PlayerLoggedInEvent,
    PlayerLoggedOutEvent,
    PlayerRespawnEvent,
)
from .server import ServerStartedEvent, ServerStartingEvent, ServerStoppingEvent, ServerTickEvent


def _register_event_wrappers() -> None:
    """Register all event wrapper classes so wrap() auto-wraps event objects."""
    _events: list[type] = [
        # Server
        ServerStartingEvent,
        ServerStartedEvent,
        ServerStoppingEvent,
        ServerTickEvent,
        # Player
        PlayerLoggedInEvent,
        PlayerLoggedOutEvent,
        PlayerRespawnEvent,
        PlayerChangedDimensionEvent,
        AttackEntityEvent,
        PlayerInteractEvent,
        # Block
        BlockBreakEvent,
        BlockPlaceEvent,
        # Entity
        LivingDeathEvent,
        LivingDamageEvent,
        EntityJoinLevelEvent,
    ]
    for evt_cls in _events:
        java_name = getattr(evt_cls, "__java_class_name__", None)
        if java_name:
            register_wrapper(java_name, evt_cls)
