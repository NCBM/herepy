from __future__ import annotations

from typing import Any, override

from ._base import JavaWrapper

# Sentinel module-level vars — set via _set_java_classes() at startup
_BlockPosClass: Any = None
_Vec3Class: Any = None
_ResourceLocationClass: Any = None
_ComponentClass: Any = None


def _set_java_classes(block_pos: Any, vec3: Any, resource_location: Any, component: Any) -> None:
    global _BlockPosClass, _Vec3Class, _ResourceLocationClass, _ComponentClass
    _BlockPosClass = block_pos
    _Vec3Class = vec3
    _ResourceLocationClass = resource_location
    _ComponentClass = component


class BlockPos(JavaWrapper[Any]):
    """Immutable integer block position. Wraps net.minecraft.core.BlockPos."""

    @property
    def x(self) -> int:
        return int(self._jobj.getX())

    @property
    def y(self) -> int:
        return int(self._jobj.getY())

    @property
    def z(self) -> int:
        return int(self._jobj.getZ())

    def offset(self, dx: int, dy: int, dz: int) -> BlockPos:
        return BlockPos(self._jobj.offset(dx, dy, dz))

    def above(self, n: int = 1) -> BlockPos:
        return BlockPos(self._jobj.above(n))

    def below(self, n: int = 1) -> BlockPos:
        return BlockPos(self._jobj.below(n))

    def __iter__(self):
        yield self.x
        yield self.y
        yield self.z

    @override
    def __repr__(self) -> str:
        return f"BlockPos({self.x}, {self.y}, {self.z})"

    def as_tuple(self) -> tuple[int, int, int]:
        return (self.x, self.y, self.z)

    @classmethod
    def of(cls, x: int, y: int, z: int) -> BlockPos:
        return cls(_BlockPosClass(x, y, z))


class Vec3(JavaWrapper[Any]):
    """Floating-point 3D vector. Wraps net.minecraft.world.phys.Vec3."""

    @property
    def x(self) -> float:
        return float(self._jobj.x)

    @property
    def y(self) -> float:
        return float(self._jobj.y)

    @property
    def z(self) -> float:
        return float(self._jobj.z)

    def length(self) -> float:
        return float(self._jobj.length())

    def length_squared(self) -> float:
        return float(self._jobj.lengthSqr())

    def add(self, other: Vec3 | tuple[float, float, float]) -> Vec3:
        if isinstance(other, Vec3):
            return Vec3(self._jobj.add(other._jobj))
        x, y, z = other
        return Vec3(self._jobj.add(x, y, z))

    def subtract(self, other: Vec3) -> Vec3:
        return Vec3(self._jobj.subtract(other._jobj))

    def scale(self, factor: float) -> Vec3:
        return Vec3(self._jobj.scale(factor))

    def dot(self, other: Vec3) -> float:
        return float(self._jobj.dot(other._jobj))

    def cross(self, other: Vec3) -> Vec3:
        return Vec3(self._jobj.cross(other._jobj))

    def normalize(self) -> Vec3:
        return Vec3(self._jobj.normalize())

    def distance_to(self, other: Vec3) -> float:
        return float(self._jobj.distanceTo(other._jobj))

    def __iter__(self):
        yield self.x
        yield self.y
        yield self.z

    @override
    def __repr__(self) -> str:
        return f"Vec3({self.x}, {self.y}, {self.z})"

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    @classmethod
    def of(cls, x: float, y: float, z: float) -> Vec3:
        return cls(_Vec3Class(x, y, z))


class ResourceLocation(JavaWrapper[Any]):
    """Namespaced resource identifier. Wraps net.minecraft.resources.ResourceLocation."""

    @property
    def namespace(self) -> str:
        return str(self._jobj.getNamespace())

    @property
    def path(self) -> str:
        return str(self._jobj.getPath())

    @override
    def __str__(self) -> str:
        return f"{self.namespace}:{self.path}"

    @override
    def __repr__(self) -> str:
        return f"ResourceLocation({self.namespace!r}, {self.path!r})"

    @classmethod
    def parse(cls, location: str) -> ResourceLocation:
        return cls(_ResourceLocationClass.parse(location))

    @classmethod
    def of(cls, namespace: str, path: str) -> ResourceLocation:
        return cls(_ResourceLocationClass.fromNamespaceAndPath(namespace, path))


class Component(JavaWrapper[Any]):
    """Styled text/chat component. Wraps net.minecraft.network.chat.Component."""

    def get_string(self) -> str:
        return str(self._jobj.getString())

    @override
    def __str__(self) -> str:
        return self.get_string()

    @classmethod
    def literal(cls, text: str) -> Component:
        return cls(_ComponentClass.literal(text))

    @classmethod
    def translatable(cls, key: str, *args: Any) -> Component:
        if args:
            return cls(_ComponentClass.translatable(key, list(args)))
        return cls(_ComponentClass.translatable(key))

    @classmethod
    def empty(cls) -> Component:
        return cls(_ComponentClass.empty())
