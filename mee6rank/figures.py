from __future__ import annotations

from typing import Any, NamedTuple, Tuple

__all__ = ("Point",)


class Point(NamedTuple):
    x: int
    y: int

    def __add__(self, other: Any) -> Point:
        return self.__class__(self.x + other[0], self.y + other[1])

    def __radd__(self, other: Any) -> Point:
        return self.__add__(other)

    def __sub__(self, other: Any) -> Point:
        return self.__class__(self.x - other[0], self.y - other[1])

    def __rsub__(self, other: Any) -> Point:
        return self.__class__(other[0] - self.x, other[1] - self.y)

    def __neg__(self) -> Point:
        return self.__class__(-self.x, -self.y)

    def to_tuple(self) -> Tuple[int, int]:
        # while Point is a tuple, it defines incompatible add and sub operations
        return (self.x, self.y)
