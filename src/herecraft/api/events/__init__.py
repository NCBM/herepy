"""herecraft.api.events — Pythonic wrappers for NeoForge events.

Usage::

    from herecraft.api.events import ServerStartingEvent, PlayerLoggedInEvent
    from herecraft.event import event

    @event
    def on_start(e: ServerStartingEvent):
        print(f"Server starting! Version: {e.server.server_version}")
"""

from ._base import Event
from .block import BlockBreakEvent, BlockPlaceEvent
from .entity import EntityJoinLevelEvent, LivingDamageEvent, LivingDeathEvent
from .player import (
    AttackEntityEvent,
    PlayerChangedDimensionEvent,
    PlayerEvent,
    PlayerInteractEvent,
    PlayerLoggedInEvent,
    PlayerLoggedOutEvent,
    PlayerRespawnEvent,
)
from .server import ServerStartedEvent, ServerStartingEvent, ServerStoppingEvent, ServerTickEvent

__all__ = [
    "AttackEntityEvent",
    "BlockBreakEvent",
    "BlockPlaceEvent",
    "EntityJoinLevelEvent",
    "Event",
    "LivingDamageEvent",
    "LivingDeathEvent",
    "PlayerChangedDimensionEvent",
    "PlayerEvent",
    "PlayerInteractEvent",
    "PlayerLoggedInEvent",
    "PlayerLoggedOutEvent",
    "PlayerRespawnEvent",
    "ServerStartedEvent",
    "ServerStartingEvent",
    "ServerStoppingEvent",
    "ServerTickEvent",
]
