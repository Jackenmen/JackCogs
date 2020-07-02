# this an incomplete stub of pillow library for use of cogs in this repo
# nobody made full stub for this library so only stuff used by this repo is typed

import pathlib
from typing import Any, BinaryIO, Optional, Text, Tuple, Union

from . import ImageFile

LURD = Tuple[int, int, int, int]  # left, up(per), right, down = x0, y0, x1, y1
XY = Tuple[int, int]
Coord = XY
Size = XY
Matrix4 = Tuple[float, float, float, float]
Matrix12 = Tuple[
    float, float, float, float, float, float, float, float, float, float, float, float
]
Mode = str
Color = Union[
    int, float, Tuple[int, int], Tuple[int, int, int], Tuple[int, int, int, int]
]

ANTIALIAS: int

class Image:
    def __init__(self) -> None: ...
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def size(self) -> Size: ...
    def __enter__(self) -> Image: ...
    def __exit__(self, *args: Any) -> None: ...
    def close(self) -> None: ...
    def __del__(self) -> None: ...
    def convert(
        self,
        mode: Optional[Mode] = ...,
        matrix: Optional[Union[Matrix4, Matrix12]] = ...,
        dither: Optional[int] = ...,
        palette: Optional[int] = ...,
        colors: int = ...,
    ) -> Image: ...
    def paste(
        self,
        im: Union[Image, Color, Text],
        box: Optional[Union[LURD, Coord]] = ...,
        mask: Optional[Image] = ...,
    ) -> None: ...
    def alpha_composite(
        self, im: Image, dest: Coord = ..., source: Union[Coord, LURD] = ...
    ) -> None: ...
    def save(
        self,
        fp: Union[Text, pathlib.Path, BinaryIO],
        format: Optional[Text] = ...,
        **params: Any
    ) -> None: ...
    def thumbnail(self, size: Size, resample: int = ...) -> None: ...
    def putalpha(self, alpha: Union[Image, int]) -> None: ...

def new(mode: Mode, size: Size, color: Optional[Union[Color, Text]] = ...) -> Image: ...
def open(
    fp: Union[Text, pathlib.Path, BinaryIO], mode: Text = ...
) -> ImageFile.ImageFile: ...
