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

from __future__ import annotations

from abc import ABC
from pathlib import Path
from typing import Any, BinaryIO, Dict, NamedTuple, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .figures import Point
from .player import PlayerWithAvatar
from .utils import natural_size


class CoordsInfo(NamedTuple):
    point: Point
    font_name: Optional[str] = None


class Mee6RankImageTemplate:
    def __init__(
        self,
        *,
        coords: Dict[str, CoordsInfo],
        fonts: Dict[str, ImageFont.ImageFont],
        avatar_mask: Path,
        card_base: Path,
        progressbar: Path,
        progressbar_rounding_mask: Path,
    ) -> None:
        self.coords = coords
        self.fonts = fonts
        self.avatar_mask = avatar_mask
        self.card_base = card_base
        self.progressbar = progressbar
        self.progressbar_rounding_mask = progressbar_rounding_mask

    def get_coords(self, coords_name: str) -> CoordsInfo:
        """Get coords for given element."""
        return self.coords[coords_name]

    def generate_image(self, player: PlayerWithAvatar) -> Mee6RankImage:
        return Mee6RankImage(self, player)


class MixinMeta(ABC):
    def __init__(self) -> None:
        self._result: Image.Image


class Mee6RankImageMixin(MixinMeta):
    def __init__(self) -> None:
        super().__init__()
        self._draw = ImageDraw.Draw(self._result)

    @property
    def size(self) -> Tuple[int, int]:
        return self._result.size

    def alpha_composite(
        self,
        im: Union[Image.Image, Mee6RankImageMixin],
        dest: Tuple[int, int] = (0, 0),
        source: Union[Tuple[int, int], Tuple[int, int, int, int]] = (0, 0),
    ) -> None:
        image = im._result if isinstance(im, Mee6RankImageMixin) else im
        self._result.alpha_composite(image, dest, source)

    def paste(
        self,
        im: Union[
            Image.Image,
            Union[
                int,
                float,
                Tuple[int, int],
                Tuple[int, int, int],
                Tuple[int, int, int, int],
            ],
            str,
            Mee6RankImageMixin,
        ],
        box: Optional[Union[Tuple[int, int], Tuple[int, int, int, int]]] = None,
        mask: Optional[Image.Image] = None,
    ) -> None:
        image = im._result if isinstance(im, Mee6RankImageMixin) else im
        self._result.paste(image, box, mask)

    def thumbnail(self, size: Tuple[int, int], resample: int = 3) -> None:
        self._result.thumbnail(size, resample)

    def save(
        self,
        fp: Union[str, Path, BinaryIO],
        format: Optional[str] = None,
        **params: Any,
    ) -> None:
        self._result.save(fp, format, **params)


class Mee6RankImage(Mee6RankImageMixin):
    def __init__(
        self, template: Mee6RankImageTemplate, player: PlayerWithAvatar
    ) -> None:
        self.template = template
        self.fonts = self.template.fonts
        self.player = player
        self._result = Image.open(self.template.card_base).convert("RGBA")
        super().__init__()
        self._generate_image()

    def __del__(self) -> None:
        self._result.close()

    def _generate_image(self) -> None:
        self._draw_level()
        self._draw_username()
        self._draw_progressbar()
        self._draw_xp()
        self._draw_avatar()

    def _draw_level(self) -> None:
        # why do I even use templates when I still do stuff like this...
        parts = {
            "level_number": (str(self.player.level), 0, "#62d3f5"),
            "level_caption": ("LEVEL", 6, "#62d3f5"),
            "rank_number": (f"#{self.player.rank}", 15, "#ffffff"),
            "rank_caption": ("RANK", 6, "#ffffff"),
        }
        offset_x = 0
        for part_name, (text, offset, fill) in parts.items():
            coords, font_name = self.template.get_coords(part_name)
            # all parts from dict above have font name defined
            assert isinstance(font_name, str), "mypy"
            font = self.fonts[font_name]
            x, offset_y = font.getsize(text)
            offset_x += x + offset
            coords -= (offset_x, offset_y)
            self._draw.text(xy=coords, text=text, fill=fill, font=font)

    def _draw_username(self) -> None:
        # Username
        # TODO: fix the math here - cut long usernames,
        # change font size for longer text, etc.
        text = self.player.member.name
        coords, font_name = self.template.get_coords("username")
        assert isinstance(font_name, str), "mypy"  # username has font name defined
        font = self.fonts[font_name]
        offset_x, offset_y = font.getsize(text)
        coords -= (0, offset_y)
        self._draw.text(xy=coords, text=text, fill="#fff", font=font)
        # discriminator
        text = f"#{self.player.member.discriminator}"
        coords, font_name = self.template.get_coords("discriminator")
        assert isinstance(font_name, str), "mypy"  # discriminator has font name defined
        font = self.fonts[font_name]
        _, offset_y = font.getsize(text)
        offset_x += 10
        coords += (offset_x, -offset_y)
        self._draw.text(xy=coords, text=text, fill="#7f8384", font=font)

    def _draw_progressbar(self) -> None:
        with Image.open(self.template.progressbar) as progressbar_top:
            result = Image.new(mode="RGBA", size=progressbar_top.size, color="#484b4e")

            # calculate progressbar width
            width = int(
                self.player.level_xp / self.player.level_total_xp * result.width
            )
            # progressbar should be either 0 or 36 when <36
            # (taken from comments in Mee6's svg)
            if width < 36 and width != 0:
                width = 36

            # make progressbar
            progressbar = Image.new(mode="RGBA", size=result.size)
            progressbar_draw = ImageDraw.Draw(progressbar)
            progressbar_draw.rectangle(xy=(0, 0, width, result.height), fill="#62d3f5")

            # make and apply rounding mask for end (right side) of the progressbar
            with Image.open(self.template.progressbar_rounding_mask).convert(
                "L"
            ) as rounding_mask:
                mask = Image.new(mode="L", size=progressbar.size, color="#ffffff")
                mask.paste(rounding_mask, (width - rounding_mask.width + 1, 0))
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rectangle(
                    xy=(width, 0, mask.width, mask.height), fill="#000000"
                )
            progressbar.putalpha(mask)

            # join everything
            result.alpha_composite(progressbar)
            result.alpha_composite(progressbar_top)

            coords, _ = self.template.get_coords("progressbar")
            self._result.alpha_composite(result, coords.to_tuple())

    def _draw_xp(self) -> None:
        # why do I even use templates when I still do stuff like this...
        parts = {
            "needed_xp": (
                f"/ {natural_size(self.player.level_total_xp)} XP",
                0,
                "#7f8384",
            ),
            "current_xp": (natural_size(self.player.level_xp), 6, "#ffffff"),
        }
        offset_x = 0
        for part_name, (text, offset, fill) in parts.items():
            coords, font_name = self.template.get_coords(part_name)
            # all parts from dict above have font name defined
            assert isinstance(font_name, str), "mypy"
            font = self.fonts[font_name]
            x, offset_y = font.getsize(text)
            offset_x += x + offset
            coords -= (offset_x, offset_y)
            self._draw.text(xy=coords, text=text, fill=fill, font=font)

    def _draw_avatar(self) -> None:
        with Image.open(self.template.avatar_mask).convert("L") as avatar_mask:
            avatar_file = self.player.avatar
            avatar_file.seek(0)
            avatar = Image.open(avatar_file).convert("RGBA")
            avatar_output = ImageOps.fit(avatar, avatar_mask.size, centering=(0.5, 0.5))
            avatar_output.putalpha(avatar_mask)
            self._result.alpha_composite(avatar_output, (40, 60))
