from typing import Tuple

__all__ = ('Point', 'Rectangle')


class Point:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

    def __getitem__(self, item) -> int:
        return (self.x, self.y)[item]

    def __iter__(self):
        for axis in (self.x, self.y):
            yield axis

    def __repr__(self) -> str:
        return f'Point({self.x}, {self.y})'

    def __len__(self) -> int:
        return 2

    def __add__(self, other) -> "Point":
        return self.__class__(self.x+other[0], self.y+other[1])

    def __radd__(self, other) -> "Point":
        return self + other

    def __sub__(self, other) -> "Point":
        return self.__class__(self.x-other[0], self.y-other[1])

    def __rsub__(self, other) -> "Point":
        return self.__class__(other[0]-self.x, other[1]-self.y)

    def __neg__(self) -> "Point":
        return self.__class__(-self.x, -self.y)

    @classmethod
    def from_tuple(cls, tup: tuple):
        return cls(*tup[:2])


class Rectangle:
    def __init__(self, point: Point, size: Tuple[int, int]):
        self.x1, self.y1 = point
        self.x2, self.y2 = point+size

    def __getitem__(self, item) -> int:
        return (self.x1, self.y1, self.x2, self.y2)[item]

    def __iter__(self):
        for corner in (self.x1, self.y1, self.x2, self.y2):
            yield corner

    def __repr__(self) -> str:
        return f'Rectangle({self.x1}, {self.y1}, {self.x2}, {self.y2})'

    def __len__(self) -> int:
        return 4

    @classmethod
    def from_tuple(cls, tup: tuple):
        return cls(*tup[:4])
