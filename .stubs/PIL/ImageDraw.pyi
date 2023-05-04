# Copyright 2018-present Jakub Kuczys (https://github.com/Jackenmen)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This an incomplete stub of pillow library for use of cogs in this repo.
Nobody have made a full stub for this library so only stuff used by this repo is typed.
"""

from typing import Any, Optional, Tuple, Union

from . import Image, ImageFont

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
