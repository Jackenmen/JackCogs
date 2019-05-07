import contextlib
from pathlib import Path
from typing import Tuple, Dict, NamedTuple, Optional, Sequence

from PIL import Image, ImageDraw, ImageFont

from .rlapi import PlaylistKey, Player
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
        images: Dict[str, str]
    ):
        self.rank_size = rank_size
        self.tier_size = tier_size
        self.offsets = offsets
        self.coords = coords
        self.fonts = fonts
        self.bg_image = bg_image
        self.images = images

    def get_coords(self, coords_name: str, playlist_key: Optional[PlaylistKey] = None):
        """Gets coords for given element in chosen playlist"""
        coords_info = self.coords[coords_name]
        if playlist_key is None:
            offset = (0, 0)
        else:
            offset = self.offsets[playlist_key]
        return CoordsInfo(coords_info.point+offset, coords_info.font_name)

    def generate_image(self, player: Player, playlists) -> 'RLStatsImage':
        return RLStatsImage(self, player, playlists)


class RLStatsImageMixin:
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


class RLStatsImage(RLStatsImageMixin):
    def __init__(
        self,
        template: RLStatsImageTemplate,
        player: Player,
        playlists: Sequence[PlaylistKey]
    ):
        self.template = template
        self.player = player
        self.playlists = playlists
        self._result = Image.open(self.template.bg_image).convert('RGBA')
        super().__init__()
        self._generate_image()

    def _generate_image(self):
        self._draw_username()
        for playlist_key in self.playlists:
            self.alpha_composite(RLStatsImagePlaylist(self, playlist_key))
        self._draw_season_rewards()

    def _draw_username(self):
        coords, font_name = self.template.get_coords('username')
        w, h = self.template.fonts[font_name].getsize(self.player.user_name)
        coords -= (w/2, h/2)
        self._draw.text(
            xy=coords,
            text=self.player.user_name,
            font=self.template.fonts[font_name],
            fill="white"
        )

    def _draw_season_rewards(self):
        self._draw_season_reward_lvl()
        self._draw_season_reward_bars()

    def _draw_season_reward_lvl(self):
        rewards = self.player.season_rewards
        coords, _ = self.template.get_coords('season_rewards_lvl')
        reward_image = Image.open(
            self.template.images['season_rewards_lvl'].format(
                rewards.level, rewards.reward_ready
            )
        ).convert('RGBA')
        self.alpha_composite(reward_image, coords.to_tuple())

    def _draw_season_reward_bars(self):
        rewards = self.player.season_rewards
        if rewards.level != 7:
            reward_bars_win_image = Image.open(
                self.template.images['season_rewards_bars_win'].format(rewards.level)
            ).convert('RGBA')
            if rewards.reward_ready:
                reward_bars_nowin_image = Image.open(
                    self.template.images['season_rewards_bars_nowin'].format(
                        rewards.level
                    )
                ).convert('RGBA')
            else:
                reward_bars_nowin_image = Image.open(
                    self.template.images['season_rewards_bars_red']
                ).convert('RGBA')
            coords, _ = self.template.get_coords('season_rewards_bars')
            for win in range(0, 10):
                coords += (83, 0)
                if rewards.wins > win:
                    self.alpha_composite(reward_bars_win_image, coords.to_tuple())
                else:
                    self.alpha_composite(reward_bars_nowin_image, coords.to_tuple())


class RLStatsImagePlaylist(RLStatsImageMixin):
    def __init__(self, img: RLStatsImage, playlist_key: PlaylistKey):
        self.template = img.template
        self.player = img.player
        self.fonts = self.template.fonts
        self._result = Image.new('RGBA', img.size)
        super().__init__()
        self.playlist_key = playlist_key
        self.playlist = self.player.get_playlist(self.playlist_key)
        self._draw_playlist()

    def get_coords(self, coords_name):
        return self.template.get_coords(coords_name, self.playlist_key)

    def _draw_playlist(self):
        self._draw_playlist_name()
        self._draw_rank_image()
        self._draw_rank_name()
        self._draw_matches_played()
        self._draw_win_streak()
        self._draw_skill_rating()
        self._draw_gain()
        self._draw_division_down()
        self._draw_tier_down()
        self._draw_division_up()
        self._draw_tier_up()

    def _draw_playlist_name(self):
        coords, font_name = self.get_coords('playlist_name')
        font = self.fonts[font_name]
        w, h = font.getsize(self.playlist_key.friendly_name)
        coords -= (w/2, h/2)
        self._draw.text(
            xy=coords,
            text=self.playlist_key.friendly_name,
            font=font,
            fill="white"
        )

    def _draw_rank_image(self):
        playlist = self.player.get_playlist(self.playlist_key)
        temp_image = Image.open(
            self.template.images['tier_image'].format(playlist.tier)
        ).convert('RGBA')
        temp_image.thumbnail(self.template.rank_size, Image.ANTIALIAS)
        coords, _ = self.get_coords('rank_image')
        self.alpha_composite(temp_image, coords.to_tuple())

    def _draw_rank_name(self):
        coords, font_name = self.get_coords('rank_text')
        playlist_name = str(self.playlist)
        font = self.fonts[font_name]
        w, h = font.getsize(playlist_name)
        coords -= (w/2, h/2)
        self._draw.text(xy=coords, text=playlist_name, font=font, fill="white")

    def _draw_matches_played(self):
        coords, font_name = self.get_coords('matches_played')
        font = self.fonts[font_name]
        self._draw.text(
            xy=coords,
            text=str(self.playlist.matches_played),
            font=font,
            fill="white"
        )

    def _draw_win_streak(self):
        if self.playlist.win_streak < 0:
            text = "Losing Streak:"
        else:
            text = "Win Streak:"
        text_coords, text_font_name = self.get_coords('win_streak_text')
        amount_coords, amount_font_name = self.get_coords('win_streak_amount')
        amount_font = self.fonts[amount_font_name]
        text_font = self.fonts[text_font_name]
        w, _ = text_font.getsize(text)
        amount_coords += (w, 0)
        # Draw - "Win Streak" or "Losing Streak"
        self._draw.text(xy=text_coords, text=text, font=text_font, fill="white")
        # Draw - amount of won/lost games
        self._draw.text(
            xy=amount_coords,
            text=str(self.playlist.win_streak),
            font=amount_font,
            fill="white"
        )

    def _draw_skill_rating(self):
        coords, font_name = self.get_coords('skill')
        font = self.fonts[font_name]
        self._draw.text(
            xy=coords,
            text=str(self.playlist.skill),
            font=font,
            fill="white"
        )

    def _draw_gain(self):
        # TODO: rltracker rewrite needed to support this
        gain = 0

        coords, font_name = self.get_coords('gain')
        font = self.fonts[font_name]
        if gain == 0:
            text = "N/A"
        else:
            text = str(round(gain, 3))
        self._draw.text(xy=coords, text=text, font=font, fill="white")

    def _draw_division_down(self):
        coords, font_name = self.get_coords('div_down')
        font = self.fonts[font_name]
        if self.playlist.tier_estimates.div_down is None:
            text = 'N/A'
        else:
            text = '{0:+d}'.format(self.playlist.tier_estimates.div_down)
        self._draw.text(xy=coords, text=text, font=font, fill="white")

    def _draw_tier_down(self):
        # Icon
        tier = self.playlist.tier_estimates.tier
        tier_down = self.template.images['tier_image'].format(
            tier-1 if tier > 0 else 0
        )
        tier_down_image = Image.open(tier_down).convert('RGBA')
        tier_down_image.thumbnail(self.template.tier_size, Image.ANTIALIAS)
        image_coords, font_name = self.get_coords('tier_down')
        font = self.fonts[font_name]
        self.alpha_composite(tier_down_image, image_coords.to_tuple())
        # Points
        if self.playlist.tier_estimates.tier_down is None:
            text = 'N/A'
        else:
            text = '{0:+d}'.format(self.playlist.tier_estimates.tier_down)
        text_coords = image_coords + (self.template.tier_size[0]+11, -5)
        self._draw.text(xy=text_coords, text=text, font=font, fill="white")

    def _draw_division_up(self):
        coords, font_name = self.get_coords('div_up')
        font = self.fonts[font_name]
        if self.playlist.tier_estimates.div_up is None:
            text = 'N/A'
        else:
            text = '{0:+d}'.format(self.playlist.tier_estimates.div_up)
        self._draw.text(xy=coords, text=text, font=font, fill="white")

    def _draw_tier_up(self):
        # Icon
        tier = self.playlist.tier_estimates.tier
        tier_up = self.template.images['tier_image'].format(
            tier+1 if 0 < tier < self.playlist.tier_max else 0
        )
        tier_up_image = Image.open(tier_up).convert('RGBA')
        tier_up_image.thumbnail(self.template.tier_size, Image.ANTIALIAS)
        image_coords, font_name = self.get_coords('tier_up')
        font = self.fonts[font_name]
        self.alpha_composite(tier_up_image, image_coords.to_tuple())
        # Points
        if self.playlist.tier_estimates.tier_up is None:
            text = 'N/A'
        else:
            text = '{0:+d}'.format(self.playlist.tier_estimates.tier_up)
        text_coords = image_coords + (self.template.tier_size[0]+11, -5)
        self._draw.text(xy=text_coords, text=text, font=font, fill="white")
