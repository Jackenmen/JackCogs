import contextlib
from pathlib import Path
from typing import NamedTuple, Optional, Dict

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .figures import Point


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
    ):
        self.coords = coords
        self.fonts = fonts
        self.avatar_mask = avatar_mask
        self.card_base = card_base
        self.progressbar = progressbar

    def get_coords(self, coords_name: str):
        """Get coords for given element."""
        return self.coords[coords_name]

    def generate_image(self, player: dict) -> "Mee6RankImage":
        return Mee6RankImage(self, player)


class Mee6RankImageMixin:
    def __init__(self):
        self._draw = ImageDraw.Draw(self._result)

    @property
    def size(self):
        return self._result.size

    def alpha_composite(self, im, dest=(0, 0), source=(0, 0)):
        with contextlib.suppress(AttributeError):
            im = im._result
        self._result.alpha_composite(im, dest, source)

    def paste(self, im, box=None, mask=None):
        with contextlib.suppress(AttributeError):
            im = im._result
        self._result.paste(im, box, mask)

    def save(self, fp, format=None, **params):
        self._result.save(fp, format, **params)


class Mee6RankImage(Mee6RankImageMixin):
    def __init__(self, template, player):
        self.template = template
        self.fonts = self.template.fonts
        self.player = player
        self._result = Image.open(self.template.card_base).convert("RGBA")
        super().__init__()
        self._generate_image()

    def _generate_image(self):
        self._draw_level()
        self._draw_username()
        self._draw_progressbar()
        self._draw_xp()
        self._draw_avatar()

    def _draw_level(self):
        # Level number
        text = str(self.player["level"])
        coords, font_name = self.template.get_coords("level_number")
        font = self.fonts[font_name]
        offset_x, offset_y = font.getsize(text)
        coords -= (offset_x, offset_y)
        self._draw.text(xy=coords, text=text, fill="#62d3f5", font=font)
        # Level caption
        coords, font_name = self.template.get_coords("level_caption")
        font = self.fonts[font_name]
        x, offset_y = font.getsize("LEVEL")
        offset_x += x + 6
        coords -= (offset_x, offset_y)
        self._draw.text(xy=coords, text="LEVEL", fill="#62d3f5", font=font)
        # Rank number
        text = f"#{self.player['rank']}"
        coords, font_name = self.template.get_coords("rank_number")
        font = self.fonts[font_name]
        x, offset_y = font.getsize(text)
        offset_x += x + 15
        coords -= (offset_x, offset_y)
        self._draw.text(xy=coords, text=text, fill="#fff", font=font)
        # Rank caption
        coords, font_name = self.template.get_coords("rank_caption")
        font = self.fonts[font_name]
        x, offset_y = font.getsize("RANK")
        offset_x += x + 6
        coords -= (offset_x, offset_y)
        self._draw.text(xy=coords, text="RANK", fill="#fff", font=font)

    def _draw_username(self):
        # Username
        text = self.player["member_obj"].name
        coords, font_name = self.template.get_coords("username")
        font = self.fonts[font_name]
        offset_x, offset_y = font.getsize(text)
        coords -= (0, offset_y)
        self._draw.text(xy=coords, text=text, fill="#fff", font=self.fonts["DejaVu40"])
        # discriminator
        text = self.player["member_obj"].discriminator
        coords, font_name = self.template.get_coords("discriminator")
        font = self.fonts[font_name]
        _, offset_y = font.getsize(text)
        offset_x += 10
        coords += (offset_x, -offset_y)
        self._draw.text(xy=coords, text=text, fill="#7f8384", font=font)

    def _draw_progressbar(self):
        progressbar_border = Image.open(self.template.progressbar)
        progressbar = Image.new(
            mode="RGBA", size=progressbar_border.size, color="#484b4e"
        )
        progressbar_draw = ImageDraw.Draw(progressbar)
        progressbar_draw.rectangle(
            xy=(0, 0, int(4446 / 11495 * progressbar.width), progressbar.height),
            fill="#62d3f5",
        )
        progressbar.alpha_composite(progressbar_border)
        coords, _ = self.template.get_coords("progressbar")
        self._result.alpha_composite(progressbar, coords.to_tuple())

    def _draw_xp(self):
        # Needed XP
        text = f"/ {self.player['detailed_xp'][1]} XP"
        coords, font_name = self.template.get_coords("needed_xp")
        font = self.fonts[font_name]
        offset_x, offset_y = font.getsize(text)
        coords -= (offset_x, offset_y)
        self._draw.text(
            xy=coords, text=text, fill="#7f8384", font=self.fonts["Poppins24"]
        )
        # Current XP
        text = str(self.player["detailed_xp"][0])
        coords, font_name = self.template.get_coords("current_xp")
        font = self.fonts[font_name]
        x, offset_y = font.getsize(text)
        offset_x += x + 6
        coords -= (offset_x, offset_y)
        self._draw.text(xy=coords, text=text, fill="#fff", font=self.fonts["Poppins24"])

    def _draw_avatar(self):
        # Avatar Generation
        avatar_mask = Image.open(self.template.avatar_mask).convert("L")
        avatar_file = self.player["avatar"]
        avatar_file.seek(0)
        avatar = Image.open(avatar_file)
        avatar_output = ImageOps.fit(avatar, (avatar_mask.size), centering=(0.5, 0.5))
        avatar_output.putalpha(avatar_mask)
        self._result.alpha_composite(avatar_output, (40, 60))
