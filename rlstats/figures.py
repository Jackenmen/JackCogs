from __future__ import annotations

from typing import Any, Iterator, Tuple

__all__ = ("Point",)


class Point:
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

    def __getitem__(self, item: int) -> int:
        return (self.x, self.y)[item]

    def __iter__(self) -> Iterator[int]:
        for axis in (self.x, self.y):
            yield axis

    def __repr__(self) -> str:
        return f"Point({self.x}, {self.y})"

    def __len__(self) -> int:
        return 2

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
        return (self.x, self.y)

    @classmethod
    def from_tuple(cls, tup: Tuple[int, int]) -> Point:
        return cls(*tup)
