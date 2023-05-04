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
from typing import Any, BinaryIO, Dict, NamedTuple, Optional, Sequence, Tuple, Union

from PIL import Image, ImageDraw, ImageFont
from rlapi import Player, Playlist, PlaylistKey

from .figures import Point


class CoordsInfo(NamedTuple):
    point: Point
    font_name: Optional[str] = None


class RLStatsImageTemplate:
    def __init__(
        self,
        *,
        rank_size: Tuple[int, int],
        tier_size: Tuple[int, int],
        offsets: Dict[PlaylistKey, Tuple[int, int]],
        coords: Dict[str, CoordsInfo],
        fonts: Dict[str, ImageFont.ImageFont],
        bg_image: Path,
        bg_overlay: int,
        rank_base: Path,
        images: Dict[str, str],
        season_rewards_colors: Dict[int, str],
    ):
        self.rank_size = rank_size
        self.tier_size = tier_size
        self.offsets = offsets
        self.coords = coords
        self.fonts = fonts
        self.bg_image = bg_image
        self.bg_overlay = bg_overlay
        self.rank_base = rank_base
        self.images = images
        self.season_rewards_colors = season_rewards_colors

    def get_coords(
        self, coords_name: str, playlist_key: Optional[PlaylistKey] = None
    ) -> CoordsInfo:
        """Gets coords for given element in chosen playlist"""
        coords_info = self.coords[coords_name]
        if playlist_key is None:
            offset = (0, 0)
        else:
            offset = self.offsets[playlist_key]
        return CoordsInfo(coords_info.point + offset, coords_info.font_name)

    def generate_image(
        self, player: Player, playlists: Tuple[PlaylistKey, ...]
    ) -> RLStatsImage:
        return RLStatsImage(self, player, playlists)


class MixinMeta(ABC):
    def __init__(self) -> None:
        self._result: Image.Image


class RLStatsImageMixin(MixinMeta):
    def __init__(self) -> None:
        super().__init__()
        self._draw = ImageDraw.Draw(self._result)

    @property
    def size(self) -> Tuple[int, int]:
        return self._result.size

    def alpha_composite(
        self,
        im: Union[Image.Image, RLStatsImageMixin],
        dest: Tuple[int, int] = (0, 0),
        source: Union[Tuple[int, int], Tuple[int, int, int, int]] = (0, 0),
    ) -> None:
        image = im._result if isinstance(im, RLStatsImageMixin) else im
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
            RLStatsImageMixin,
        ],
        box: Optional[Union[Tuple[int, int], Tuple[int, int, int, int]]] = None,
        mask: Optional[Image.Image] = None,
    ) -> None:
        image = im._result if isinstance(im, RLStatsImageMixin) else im
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


class RLStatsImage(RLStatsImageMixin):
    def __init__(
        self,
        template: RLStatsImageTemplate,
        player: Player,
        playlists: Sequence[PlaylistKey],
    ) -> None:
        self.template = template
        self.player = player
        self.playlists = playlists
        self._result = Image.open(self.template.bg_image).convert("RGBA")
        super().__init__()
        self._generate_image()

    def __del__(self) -> None:
        self._result.close()

    def _generate_image(self) -> None:
        self._draw_bg_overlay()
        self._draw_rank_base()
        self._draw_username()
        for playlist_key in self.playlists:
            self.alpha_composite(RLStatsImagePlaylist(self, playlist_key))
        self._draw_season_rewards()

    def _draw_bg_overlay(self) -> None:
        self.alpha_composite(
            Image.new(
                "RGBA",
                self.size,
                color=(0, 0, 0, int(self.template.bg_overlay * 255 / 100)),
            )
        )

    def _draw_rank_base(self) -> None:
        with Image.open(self.template.rank_base) as im:
            self.alpha_composite(im.convert("RGBA"))

    def _draw_username(self) -> None:
        username_coords, font_name = self.template.get_coords("username")
        assert isinstance(font_name, str), "mypy"  # username has font name defined
        font = self.template.fonts[font_name]
        assert self.player.user_name is not None, "incorrect typing upstream"
        w, h = font.getsize(self.player.user_name)
        coords = username_coords - (w / 2, h / 2)
        self._draw.text(xy=coords, text=self.player.user_name, font=font, fill="white")
        self._draw_platform(w)

    def _draw_platform(self, w: int) -> None:
        coords, font_name = self.template.get_coords("platform")
        with Image.open(
            self.template.images["platform_image"].format(self.player.platform.name)
        ) as platform_image:
            coords += (w // 2, -(platform_image.height // 2))
            self.alpha_composite(platform_image.convert("RGBA"), coords.to_tuple())

    def _draw_season_rewards(self) -> None:
        self._draw_season_reward_lvl()
        if self.player.season_rewards.level != 8:
            self._draw_season_reward_bars()
            self._draw_season_reward_wins()

    def _draw_season_reward_lvl(self) -> None:
        rewards = self.player.season_rewards
        coords, _ = self.template.get_coords("season_rewards_lvl")
        with Image.open(
            self.template.images["season_rewards_lvl"].format(
                rewards.level, rewards.can_advance
            )
        ) as reward_image:
            self.alpha_composite(reward_image.convert("RGBA"), coords.to_tuple())

    def _draw_season_reward_bars(self) -> None:
        rewards = self.player.season_rewards
        reward_bars_win_image = Image.open(
            self.template.images["season_rewards_bars_win"].format(rewards.level)
        ).convert("RGBA")
        if rewards.can_advance:
            reward_bars_nowin_image = Image.open(
                self.template.images["season_rewards_bars_nowin"].format(rewards.level)
            ).convert("RGBA")
        else:
            reward_bars_nowin_image = Image.open(
                self.template.images["season_rewards_bars_red"]
            ).convert("RGBA")
        coords, _ = self.template.get_coords("season_rewards_bars")
        for win in range(0, 10):
            coords += (83, 0)
            if rewards.wins > win:
                self.alpha_composite(reward_bars_win_image, coords.to_tuple())
            else:
                self.alpha_composite(reward_bars_nowin_image, coords.to_tuple())
        reward_bars_win_image.close()
        reward_bars_nowin_image.close()

    def _draw_season_reward_wins(self) -> None:
        rewards = self.player.season_rewards
        coords, _ = self.template.get_coords("season_rewards_wins_text")
        if rewards.can_advance:
            wins_text_image = Image.open(
                self.template.images["season_rewards_wins_white"]
            )
            fill = self.template.season_rewards_colors[rewards.level]
        else:
            wins_text_image = Image.open(
                self.template.images["season_rewards_wins_red"]
            )
            fill = self.template.season_rewards_colors[-1]
        with wins_text_image:
            self.alpha_composite(wins_text_image, coords.to_tuple())

        coords, font_name = self.template.get_coords("season_rewards_wins_max")
        # season_rewards_wins_max has font name defined
        assert isinstance(font_name, str), "mypy"
        font = self.template.fonts[font_name]
        # TODO: rlapi package should define max
        w, h = font.getsize("10")
        coords -= (w, h / 2)
        self._draw.text(xy=coords, text="10", font=font, fill=fill)

        coords, font_name = self.template.get_coords("season_rewards_wins_amount")
        # season_rewards_wins_amount has font name defined
        assert isinstance(font_name, str), "mypy"
        font = self.template.fonts[font_name]
        text = str(rewards.wins)
        w, h = font.getsize(text)
        coords -= (w, h / 2)
        self._draw.text(xy=coords, text=text, font=font, fill=fill)


class RLStatsImagePlaylist(RLStatsImageMixin):
    def __init__(self, img: RLStatsImage, playlist_key: PlaylistKey) -> None:
        self.template = img.template
        self.player = img.player
        self.fonts = self.template.fonts
        self._result = Image.new("RGBA", img.size)
        super().__init__()
        self.playlist_key = playlist_key
        playlist = self.player.get_playlist(self.playlist_key)
        # this assert *should* be safe
        assert isinstance(playlist, Playlist), "mypy"
        self.playlist: Playlist = playlist
        self._draw_playlist()

    def get_coords(self, coords_name: str) -> CoordsInfo:
        return self.template.get_coords(coords_name, self.playlist_key)

    def _draw_playlist(self) -> None:
        self._draw_playlist_name()
        self._draw_rank_image()
        self._draw_rank_name()
        self._draw_matches_played()
        self._draw_win_streak()
        self._draw_skill_rating()
        self._draw_gain()
        self._draw_estimates()

    def _draw_playlist_name(self) -> None:
        coords, font_name = self.get_coords("playlist_name")
        assert isinstance(font_name, str), "mypy"  # playlist_name has font name defined
        font = self.fonts[font_name]
        playlist_name = str(self.playlist_key)
        w, h = font.getsize(playlist_name)
        coords -= (w / 2, h / 2)
        self._draw.text(xy=coords, text=playlist_name, font=font, fill="white")

    def _draw_rank_image(self) -> None:
        with Image.open(
            self.template.images["tier_image"].format(self.playlist.tier)
        ) as im:
            rank_image = im.convert("RGBA")
            rank_image.thumbnail(self.template.rank_size, Image.ANTIALIAS)
            coords, _ = self.get_coords("rank_image")
            coords -= (rank_image.width // 2, rank_image.height // 2)
            self.alpha_composite(rank_image, coords.to_tuple())

    def _draw_rank_name(self) -> None:
        coords, font_name = self.get_coords("rank_text")
        playlist_name = str(self.playlist)
        assert isinstance(font_name, str), "mypy"  # rank_text has font name defined
        font = self.fonts[font_name]
        w, h = font.getsize(playlist_name)
        coords -= (w / 2, h / 2)
        self._draw.text(xy=coords, text=playlist_name, font=font, fill="white")

    def _draw_matches_played(self) -> None:
        coords, font_name = self.get_coords("matches_played")
        # matches_played has font name defined
        assert isinstance(font_name, str), "mypy"
        font = self.fonts[font_name]
        self._draw.text(
            xy=coords, text=str(self.playlist.matches_played), font=font, fill="white"
        )

    def _draw_win_streak(self) -> None:
        if self.playlist.win_streak < 0:
            text = "Losing Streak:"
        else:
            text = "Win Streak:"
        text_coords, text_font_name = self.get_coords("win_streak_text")
        amount_coords, amount_font_name = self.get_coords("win_streak_amount")
        # win_streak_text has font name defined
        assert isinstance(text_font_name, str), "mypy"
        # win_streak_amount has font name defined
        assert isinstance(amount_font_name, str), "mypy"
        text_font = self.fonts[text_font_name]
        amount_font = self.fonts[amount_font_name]
        w, _ = text_font.getsize(text)
        amount_coords += (w, 0)
        # Draw - "Win Streak" or "Losing Streak"
        self._draw.text(xy=text_coords, text=text, font=text_font, fill="white")
        # Draw - amount of won/lost games
        self._draw.text(
            xy=amount_coords,
            text=str(self.playlist.win_streak),
            font=amount_font,
            fill="white",
        )

    def _draw_skill_rating(self) -> None:
        coords, font_name = self.get_coords("skill")
        assert isinstance(font_name, str), "mypy"  # skill has font name defined
        font = self.fonts[font_name]
        self._draw.text(
            xy=coords, text=str(self.playlist.skill), font=font, fill="white"
        )

    def _draw_gain(self) -> None:
        # TODO: rltracker rewrite needed to support this
        gain = 0

        coords, font_name = self.get_coords("gain")
        assert isinstance(font_name, str), "mypy"  # gain has font name defined
        font = self.fonts[font_name]
        if gain == 0:
            text = "N/A"
        else:
            text = str(round(gain, 3))
        self._draw.text(xy=coords, text=text, font=font, fill="white")

    def _draw_estimates(self) -> None:
        # Icon
        tier = self.playlist.tier_estimates.tier
        attrs = {
            "div_down": None,
            "div_up": None,
            "tier_down": self.template.images["tier_image"].format(
                tier - 1 if tier > 0 else 0
            ),
            "tier_up": self.template.images["tier_image"].format(
                tier + 1 if 0 < tier < self.playlist.TIER_MAX else 0
            ),
        }
        for attr_name, tier_image_path in attrs.items():
            coords, font_name = self.get_coords(attr_name)
            # div_down, div_up, tier_down and tier_up have font name defined
            assert isinstance(font_name, str), "mypy"
            font = self.fonts[font_name]
            # Points
            points = getattr(self.playlist.tier_estimates, attr_name)
            if points is None:
                text = "N/A"
            else:
                text = f"{points:+d}"
            # tier_down/tier_up image
            if tier_image_path is not None:
                with Image.open(tier_image_path) as im:
                    tier_image = im.convert("RGBA")
                    tier_image.thumbnail(self.template.tier_size, Image.ANTIALIAS)
                    self.alpha_composite(tier_image, coords.to_tuple())
                text_coords = coords + (self.template.tier_size[0] + 11, -5)
            else:
                text_coords = coords

            self._draw.text(xy=text_coords, text=text, font=font, fill="white")
