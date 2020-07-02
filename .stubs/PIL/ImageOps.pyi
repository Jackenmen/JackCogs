# this an incomplete stub of pillow library for use of cogs in this repo
# nobody made full stub for this library so only stuff used by this repo is typed

from typing import Tuple
from . import Image

XY = Tuple[int, int]
Coord = XY
Size = XY

def fit(
    image: Image.Image,
    size: Size,
    method: int = ...,
    bleed: float = ...,
    centering: Tuple[float, float] = ...,
) -> Image.Image: ...
