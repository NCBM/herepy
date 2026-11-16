from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

from ._base import JavaWrapper
from .core import BlockPos, Component, ResourceLocation

if TYPE_CHECKING:
    from .entities import Entity, Player


class BlockState(JavaWrapper[Any]):
    """Block state at a position. Wraps net.minecraft.world.level.block.state.BlockState."""

    @property
    def block(self) -> ResourceLocation:
        return ResourceLocation(self._jobj.getBlock().builtInRegistryHolder().key().location())

    @property
    def is_air(self) -> bool:
        return bool(self._jobj.isAir())

    @property
    def is_solid(self) -> bool:
        return bool(self._jobj.isSolid())

    @override
    def __repr__(self) -> str:
        return f"BlockState({self.block})"


class Level(JavaWrapper[Any]):
    """A game dimension. Wraps net.minecraft.world.level.Level."""

    @property
    def dimension(self) -> ResourceLocation:
        return ResourceLocation(self._jobj.dimension().location())

    @property
    def is_client_side(self) -> bool:
        return bool(self._jobj.isClientSide())

    @property
    def day_time(self) -> int:
        return int(self._jobj.getDayTime())

    @property
    def game_time(self) -> int:
        return int(self._jobj.getGameTime())

    @property
    def is_raining(self) -> bool:
        return bool(self._jobj.isRaining())

    @property
    def is_thundering(self) -> bool:
        return bool(self._jobj.isThundering())

    @property
    def max_build_height(self) -> int:
        return int(self._jobj.getMaxBuildHeight())

    @property
    def min_build_height(self) -> int:
        return int(self._jobj.getMinBuildHeight())

    def get_block_state(self, pos: BlockPos) -> BlockState:
        return BlockState(self._jobj.getBlockState(pos._jobj))

    def set_block(self, pos: BlockPos, state: BlockState, flags: int = 3) -> bool:
        """Set a block. flags=3 means update+notify (standard)."""
        return bool(self._jobj.setBlock(pos._jobj, state._jobj, flags))

    def is_loaded(self, pos: BlockPos) -> bool:
        return bool(self._jobj.isLoaded(pos._jobj))

    def get_players(self) -> list[Player]:
        from .entities import Player

        return [Player(p) for p in self._jobj.players()]

    def spawn_entity(self, entity: Entity) -> bool:
        return bool(self._jobj.addFreshEntity(entity._jobj))


class Server(JavaWrapper[Any]):
    """Minecraft server. Wraps net.minecraft.server.MinecraftServer."""

    @property
    def motd(self) -> str:
        return str(self._jobj.getMotd())

    @property
    def max_players(self) -> int:
        return int(self._jobj.getMaxPlayers())

    @property
    def online_player_count(self) -> int:
        return int(self._jobj.getPlayerCount())

    @property
    def average_tick_time(self) -> float:
        return float(self._jobj.getAverageTickTime())

    @property
    def tick_count(self) -> int:
        return int(self._jobj.getTickCount())

    @property
    def server_version(self) -> str:
        return str(self._jobj.getServerVersion())

    def get_players(self) -> list[Player]:
        from .entities import Player

        jlist = self._jobj.getPlayerList().getPlayers()
        return [Player(p) for p in jlist]

    def get_player_by_name(self, name: str) -> Player | None:
        from .entities import Player

        jplayer = self._jobj.getPlayerList().getPlayerByName(name)
        if jplayer is None:
            return None
        return Player(jplayer)

    def get_overworld(self) -> Level:
        return Level(self._jobj.overworld())

    def get_level(self, dimension: str | ResourceLocation) -> Level | None:
        if isinstance(dimension, str):
            dimension = ResourceLocation.parse(dimension)
        jlevel = self._jobj.getLevel(dimension._jobj)
        if jlevel is None:
            return None
        return Level(jlevel)

    def broadcast_message(self, text: str | Component) -> None:
        msg = Component.literal(text) if isinstance(text, str) else text
        self._jobj.getPlayerList().broadcastSystemMessage(msg._jobj, False)

    def run_command(self, command: str) -> int:
        """Execute a command as the server. Returns result code."""
        source = self._jobj.createCommandSourceStack()
        return int(self._jobj.getCommands().performPrefixedCommand(source, command))
