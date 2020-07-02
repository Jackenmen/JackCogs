# this an incomplete stub of pillow library for use of cogs in this repo
# nobody made full stub for this library so only stuff used by this repo is typed

from . import Image, ImageFont
from typing import Any, Optional, Tuple, Union

LURD = Tuple[int, int, int, int]  # left, up(per), right, down = x0, y0, x1, y1
XY = Tuple[int, int]
Coord = XY
Mode = str
Color = Union[
    int, float, Tuple[int, int], Tuple[int, int, int], Tuple[int, int, int, int]
]

class ImageDraw:
    # not very correct but good enough for my usage
    def text(
        self,
        xy: Coord,
        text: str,
        fill: Optional[Union[Color, str]] = ...,
        font: Optional[ImageFont.ImageFont] = ...,
        anchor: Optional[Any] = ...,
        spacing: int = ...,
        align: str = ...,
        direction: Optional[Any] = ...,
        features: Optional[Any] = ...,
        language: Optional[Any] = ...,
        stroke_width: int = ...,
        stroke_fill: Optional[Union[Color, str]] = ...,
        *args: Any,
        **kwargs: Any,
    ) -> None: ...

    def rectangle(
        self,
        xy: LURD,
        fill: Optional[Union[Color, str]] = ...,
        outline: Optional[Union[Color, str]] = ...,
        width: int = ...,
    ) -> None: ...

def Draw(im: Image.Image, mode: Optional[Mode] = ...) -> ImageDraw: ...
