from __future__ import annotations

from typing import ClassVar

from herecraft.api.world import Server

from ._base import Event, Side


class ServerStartingEvent(Event):
    """Wraps net.neoforged.neoforge.event.server.ServerStartingEvent."""

    __java_class_name__: ClassVar[str] = "net.neoforged.neoforge.event.server.ServerStartingEvent"
    __side__: ClassVar[Side] = Side.BOTH

    @property
    def server(self) -> Server:
        return Server(self._jobj.getServer())


class ServerStartedEvent(Event):
    """Wraps net.neoforged.neoforge.event.server.ServerStartedEvent."""

    __java_class_name__: ClassVar[str] = "net.neoforged.neoforge.event.server.ServerStartedEvent"
    __side__: ClassVar[Side] = Side.BOTH

    @property
    def server(self) -> Server:
        return Server(self._jobj.getServer())


class ServerStoppingEvent(Event):
    """Wraps net.neoforged.neoforge.event.server.ServerStoppingEvent."""

    __java_class_name__: ClassVar[str] = "net.neoforged.neoforge.event.server.ServerStoppingEvent"
    __side__: ClassVar[Side] = Side.BOTH

    @property
    def server(self) -> Server:
        return Server(self._jobj.getServer())


class ServerTickEvent(Event):
    """Wraps net.neoforged.neoforge.event.tick.ServerTickEvent."""

    __java_class_name__: ClassVar[str] = "net.neoforged.neoforge.event.tick.ServerTickEvent"
    __side__: ClassVar[Side] = Side.BOTH

    @property
    def server(self) -> Server:
        return Server(self._jobj.getServer())
