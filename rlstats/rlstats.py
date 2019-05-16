import asyncio
import contextlib
import logging
import os
from io import BytesIO
from typing import List, Tuple, Optional, Iterable

import discord
from redbot.core import commands, checks
from redbot.core.config import Config
from redbot.core.utils.predicates import ReactionPredicate
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.data_manager import bundled_data_path, cog_data_path

try:
    from PIL import Image, ImageFont
except ImportError:
    raise RuntimeError("Can't load pillow. Do 'pip3 install pillow'.")

from . import rlapi
from .figures import Point
from . import errors
from .image import CoordsInfo, RLStatsImageTemplate

log = logging.getLogger('redbot.rlstats')


class RLStats(commands.Cog):
    """Get your Rocket League stats with a single command!"""

    RANK_SIZE = (179, 179)
    TIER_SIZE = (49, 49)
    OFFSETS = {
        # competitive
        rlapi.PlaylistKey.SOLO_DUEL: (0, 0),
        rlapi.PlaylistKey.DOUBLES: (960, 0),
        rlapi.PlaylistKey.SOLO_STANDARD: (0, 383),
        rlapi.PlaylistKey.STANDARD: (960, 383),
        # extra modes
        rlapi.PlaylistKey.HOOPS: (0, 0),
        rlapi.PlaylistKey.RUMBLE: (960, 0),
        rlapi.PlaylistKey.DROPSHOT: (0, 383),
        rlapi.PlaylistKey.SNOW_DAY: (960, 383)
    }
    COORDS = {
        'username': CoordsInfo(Point(960, 71), 'RobotoCondensedBold90'),
        'playlist_name': CoordsInfo(Point(243, 197), 'RobotoRegular74'),
        'rank_image': CoordsInfo(Point(153, 248), None),
        'rank_text': CoordsInfo(Point(242, 453), 'RobotoLight45'),
        'matches_played': CoordsInfo(Point(822, 160), 'RobotoBold45'),
        'win_streak_text': CoordsInfo(Point(492, 216), 'RobotoLight45'),
        'win_streak_amount': CoordsInfo(Point(503, 216), 'RobotoBold45'),
        'skill': CoordsInfo(Point(729, 272), 'RobotoBold45'),
        'gain': CoordsInfo(Point(715, 328), 'RobotoBold45'),
        'div_down': CoordsInfo(Point(552, 384), 'RobotoBold45'),
        'div_up': CoordsInfo(Point(727, 384), 'RobotoBold45'),
        'tier_down': CoordsInfo(Point(492, 446), 'RobotoBold45'),
        'tier_up': CoordsInfo(Point(667, 446), 'RobotoBold45'),
        'season_rewards_lvl': CoordsInfo(Point(150, 886), None),
        'season_rewards_bars': CoordsInfo(Point(831, 921), None)
    }

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6672039729,
                                      force_registration=True)
        self.config.register_global(
            tier_breakdown={}, competitive_overlay=40, extramodes_overlay=70
        )
        self.config.register_user(player_id=None, platform=None)
        self.rlapi_client = None
        self.bundled_data_path = bundled_data_path(self)
        self.cog_data_path = cog_data_path(self)
        self.fonts = {
            'RobotoCondensedBold90': ImageFont.truetype(
                str(self.bundled_data_path / "fonts/RobotoCondensedBold.ttf"), 90
            ),
            'RobotoRegular74': ImageFont.truetype(
                str(self.bundled_data_path / "fonts/RobotoRegular.ttf"), 74
            ),
            'RobotoBold45': ImageFont.truetype(
                str(self.bundled_data_path / "fonts/RobotoBold.ttf"), 45
            ),
            'RobotoLight45': ImageFont.truetype(
                str(self.bundled_data_path / "fonts/RobotoLight.ttf"), 45
            )
        }
        self.images = {
            'tier_image': str(self.bundled_data_path) + '/images/ranks/{}.png',
            'season_rewards_lvl': (
                str(self.bundled_data_path) + '/images/rewards/{:d}_{:d}.png'
            ),
            'season_rewards_bars_win': (
                str(self.bundled_data_path) + '/images/rewards/bars/Bar_{:d}_Win.png'
            ),
            'season_rewards_bars_nowin': (
                str(self.bundled_data_path) + '/images/rewards/bars/Bar_{:d}_NoWin.png'
            ),
            'season_rewards_bars_red': (
                str(self.bundled_data_path) + '/images/rewards/bars/Bar_Red.png'
            ),
        }
        self.rank_base = self.bundled_data_path / 'rank_base.png'
        bg_image = self.cog_data_path / 'bgs/competitive.png'
        if not bg_image.is_file():
            bg_image = self.bundled_data_path / 'bgs/competitive.png'
        self.competitive_template = RLStatsImageTemplate(
            rank_size=self.RANK_SIZE,
            tier_size=self.TIER_SIZE,
            offsets=self.OFFSETS,
            coords=self.COORDS,
            fonts=self.fonts,
            bg_image=bg_image,
            bg_overlay=40,
            rank_base=self.rank_base,
            images=self.images
        )
        bg_image = self.cog_data_path / 'bgs/extramodes.png'
        if not bg_image.is_file():
            bg_image = self.bundled_data_path / 'bgs/extramodes.png'
        self.extramodes_template = RLStatsImageTemplate(
            rank_size=self.RANK_SIZE,
            tier_size=self.TIER_SIZE,
            offsets=self.OFFSETS,
            coords=self.COORDS,
            fonts=self.fonts,
            bg_image=bg_image,
            bg_overlay=70,
            rank_base=self.rank_base,
            images=self.images
        )

    async def initialize(self):
        tier_breakdown = self.config.tier_breakdown
        self.rlapi_client = rlapi.Client(
            await self._get_token(),
            loop=self.bot.loop,
            tier_breakdown=self._convert_numbers_in_breakdown(await tier_breakdown())
        )
        await self.rlapi_client.setup
        await tier_breakdown.set(self.rlapi_client.tier_breakdown)
        self.extramodes_template.bg_overlay = await self.config.extramodes_overlay()
        self.competitive_template.bg_overlay = await self.config.competitive_overlay()

    def cog_unload(self):
        self.rlapi_client.destroy()

    __del__ = cog_unload

    def _convert_numbers_in_breakdown(self, d: dict, curr_lvl: int = 0):
        """Converts (recursively) dictionary's keys with numbers to integers"""
        new = {}
        func = self._convert_numbers_in_breakdown if curr_lvl < 2 else lambda v, _: v
        for k, v in d.items():
            v = func(v, curr_lvl+1)
            new[int(k)] = v
        return new

    async def _get_token(self):
        rocket_league = await self.bot.db.api_tokens.get_raw(
            "rocket_league", default={"user_token": ""}
        )
        return rocket_league.get('user_token', "")

    @checks.is_owner()
    @commands.group(name="rlset")
    async def rlset(self, ctx):
        """RLStats configuration options."""

    @rlset.command()
    async def token(self, ctx):
        """Instructions to set the Rocket League API tokens."""
        message = (
            "**Getting API access from Psyonix is very hard right now, "
            "it's even harder than it was, but you can try:**\n"
            "1. Go to Psyonix support website and log in with your game account\n"
            "(https://support.rocketleague.com)\n"
            '2. Click "Submit a ticket"\n'
            '3. Under "Issue" field, select '
            '"Installation and setup > I need API access"\n'
            "4. Fill out the form provided with your request, etc.\n"
            '5. Click "Submit"\n'
            "6. Hope that Psyonix will reply to you\n"
            "7. When you get API access, copy your user token "
            "from your account on Rocket League API website\n"
            f"`{ctx.prefix}set api rocket_league user_token,your_user_token`"
        )
        await ctx.maybe_send_embed(message)

    @rlset.command(name="updatebreakdown")
    async def updatebreakdown(self, ctx):
        """Update tier breakdown."""
        await ctx.send("Updating tier breakdown...")
        async with ctx.typing():
            await self.rlapi_client.update_tier_breakdown()
            await self.config.tier_breakdown.set(self.rlapi_client.tier_breakdown)
        await ctx.send("Tier breakdown updated.")

    @rlset.group(name="image")
    async def rlset_bgimage(self, ctx):
        """Set background for stats image."""

    @rlset_bgimage.group(name="extramodes")
    async def rlset_bgimage_extramodes(self, ctx):
        """Options for background for extra modes stats image."""

    @rlset_bgimage_extramodes.command("set")
    async def rlset_bgimage_extramodes_set(self, ctx):
        """
        Set background for extra modes stats image.

        Use `[p]rlset bgimage extramodes reset` to reset to default.
        """
        await self._rlset_bgimage_set(
            ctx, self.cog_data_path / 'bgs/extramodes.png', self.extramodes_template
        )

    @rlset_bgimage_extramodes.command("reset")
    async def rlset_bgimage_extramodes_reset(self, ctx):
        """Reset background for extra modes stats image to default."""
        await self._rlset_bgimage_reset(
            ctx,
            'extra modes',
            self.cog_data_path / 'bgs/extramodes.png',
            self.bundled_data_path / 'bgs/extramodes.png',
            self.extramodes_template
        )

    @rlset_bgimage_extramodes.command("overlay")
    async def rlset_bgimage_extramodes_overlay(
        self, ctx, percentage: Optional[int] = None
    ):
        """
        Set overlay percentage for extra modes stats image.

        Leave empty to reset to default (70)
        """
        await self._rlset_bgimage_overlay(
            ctx, percentage,
            'extra modes',
            self.config.extramodes_overlay,
            self.extramodes_template
        )

    @rlset_bgimage.group(name="competitive")
    async def rlset_bgimage_competitive(self, ctx):
        """Options for background for competitive stats image."""

    @rlset_bgimage_competitive.command("set")
    async def rlset_bgimage_competitive_set(self, ctx):
        """
        Set background for competitive stats image.

        Use `[p]rlset bgimage competitive reset` to reset to default.
        """
        await self._rlset_bgimage_set(
            ctx, self.cog_data_path / 'bgs/competitive.png', self.competitive_template
        )

    @rlset_bgimage_competitive.command("reset")
    async def rlset_bgimage_competitive_reset(self, ctx):
        """Reset background for competitive stats image to default."""
        await self._rlset_bgimage_reset(
            ctx,
            'competitive',
            self.cog_data_path / 'bgs/competitive.png',
            self.bundled_data_path / 'bgs/competitive.png',
            self.competitive_template
        )

    @rlset_bgimage_competitive.command("overlay")
    async def rlset_bgimage_competitive_overlay(
        self, ctx, percentage: Optional[int] = None
    ):
        """
        Set overlay percentage for competitive stats image.

        Leave empty to reset to default (40)
        """
        await self._rlset_bgimage_overlay(
            ctx, percentage,
            'competitive',
            self.config.competitive_overlay,
            self.competitive_template
        )

    async def _rlset_bgimage_set(self, ctx, filename, template):
        if not ctx.message.attachments:
            return await ctx.send("You have to send background image.")
        if len(ctx.message.attachments) > 1:
            return await ctx.send("You can send only one attachment.")
        a = ctx.message.attachments[0]
        fp = BytesIO()
        await a.save(fp)
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        try:
            im = Image.open(fp)
        except IOError:
            return await ctx.send("Attachment couldn't be open.")
        try:
            im.convert('RGBA').save(filename, 'PNG', quality=100)
        except FileNotFoundError:
            return await ctx.send("Attachment couldn't be saved.")
        template.bg_image = filename
        return await ctx.send("Background image was successfully set.")

    async def _rlset_bgimage_reset(
        self, ctx, mode, custom_filename, default_filename, template
    ):
        try:
            os.remove(custom_filename)
        except FileNotFoundError:
            await ctx.send(
                f"There was no custom background set for {mode} stats image."
            )
        else:
            await ctx.send(
                f"Background for {mode} stats image is changed back to default."
            )
            template.bg_image = default_filename

    async def _rlset_bgimage_overlay(self, ctx, percentage, mode, value_obj, template):
        if percentage is None:
            await value_obj.clear()
            template.bg_overlay = await value_obj()
            return await ctx.send(f"Overlay percentage for {mode} stats image reset.")
        if not 0 <= percentage <= 100:
            return await ctx.send("Percentage value has to be in range 0-100.")
        await value_obj.set(percentage)
        template.bg_overlay = percentage
        await ctx.send(f"Overlay percentage for {mode} stats set to {percentage}%")

    async def _get_player_data_by_user(self, user):
        """nwm"""
        user_data = await self.config.user(user).all()
        player_id, platform = user_data['player_id'], user_data['platform']
        if player_id is not None:
            return (player_id, rlapi.Platform[platform])
        raise errors.PlayerDataNotFound(
            f"Couldn't find player data for discord user with ID {user.id}"
        )

    async def _get_players(self, player_ids):
        players = []
        for player_id, platform in player_ids:
            with contextlib.suppress(rlapi.PlayerNotFound):
                players += await self.rlapi_client.get_player(player_id, platform)
        if not players:
            raise rlapi.PlayerNotFound
        return tuple(players)

    async def _choose_player(self, ctx, players: Iterable[rlapi.Player]):
        players_len = len(players)
        if players_len > 1:
            description = ''
            for idx, player in enumerate(players, 1):
                description += "\n{}. {} account with username: {}".format(
                    idx, player.platform, player.user_name
                )
            msg = await ctx.send(embed=discord.Embed(
                title="There are multiple accounts with provided name:",
                description=description
            ))

            emojis = ReactionPredicate.NUMBER_EMOJIS[1:players_len+1]
            start_adding_reactions(msg, emojis)
            pred = ReactionPredicate.with_emojis(emojis, msg)

            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=15)
            except asyncio.TimeoutError:
                raise errors.NoChoiceError(
                    "User didn't choose profile he wants to check"
                )
            finally:
                await msg.delete()

            return players[pred.result]
        return players[0]

    @commands.command()
    async def rlstats(self, ctx, *, player_id=None):
        """Checks for your or given player's Rocket League competitive stats"""
        playlists = (
            rlapi.PlaylistKey.SOLO_DUEL,
            rlapi.PlaylistKey.DOUBLES,
            rlapi.PlaylistKey.SOLO_STANDARD,
            rlapi.PlaylistKey.STANDARD
        )
        await self._rlstats_logic(ctx, self.competitive_template, playlists, player_id)

    @commands.command()
    async def rlsports(self, ctx, *, player_id=None):
        """Checks for your or given player's Rocket League extra modes stats"""
        playlists = (
            rlapi.PlaylistKey.HOOPS,
            rlapi.PlaylistKey.RUMBLE,
            rlapi.PlaylistKey.DROPSHOT,
            rlapi.PlaylistKey.SNOW_DAY
        )
        await self._rlstats_logic(ctx, self.extramodes_template, playlists, player_id)

    async def _rlstats_logic(self, ctx, template, playlists, player_id):
        await ctx.trigger_typing()

        token = await self._get_token()
        if not token:
            return await ctx.send((
                "`This cog wasn't configured properly. "
                "If you're the owner, setup the cog using {}rlset`"
            ).format(ctx.prefix))
        self.rlapi_client.update_token(token)

        player_ids: List[Tuple[str, Optional[rlapi.Platform]]] = []
        if player_id is None:
            try:
                player_ids.append(await self._get_player_data_by_user(ctx.author))
            except errors.PlayerDataNotFound:
                return await ctx.send((
                    "Your game account is not connected with Discord. "
                    "If you want to get stats, "
                    "either give your player ID after a command: "
                    "`{0}rlstats <player_id>`"
                    " or connect your account using command: "
                    "`{0}rlconnect <player_id>`"
                ).format(ctx.prefix))
        else:
            try:
                user = await commands.MemberConverter().convert(ctx, player_id)
            except commands.BadArgument:
                pass
            else:
                with contextlib.suppress(errors.PlayerDataNotFound):
                    player_ids.append(await self._get_player_data_by_user(user))
            player_ids.append((player_id, None))

        try:
            players = await self._get_players(player_ids)
        except rlapi.HTTPException as e:
            log.error(str(e))
            return await ctx.send(
                "Rocket League API experiences some issues right now. Try again later."
            )
        except rlapi.PlayerNotFound as e:
            log.debug(str(e))
            return await ctx.send(
                "The specified profile could not be found."
            )

        try:
            player = await self._choose_player(ctx, players)
        except errors.NoChoiceError as e:
            log.debug(e)
            return await ctx.send("You didn't choose profile you want to check.")

        # TODO: This should probably be handled in rlapi module
        for playlist_key in playlists:
            if playlist_key not in player.playlists:
                player.add_playlist({'playlist': playlist_key.value})

        result = template.generate_image(player, playlists)
        fp = BytesIO()
        result.save(fp, 'PNG', quality=100)
        fp.seek(0)
        await ctx.send(
            (
                'Rocket League Stats for **{}** '
                '*(arrows show amount of points for division down/up)*'
            ).format(player.user_name),
            file=discord.File(fp, '{}_profile.png'.format(player.player_id))
        )

    @commands.command()
    async def rlconnect(self, ctx, player_id):
        """Connects game profile with Discord."""
        try:
            players = await self.rlapi_client.get_player(player_id)
        except rlapi.HTTPException as e:
            log.error(str(e))
            return await ctx.send(
                "Rocket League API expierences some issues right now. Try again later."
            )
        except rlapi.PlayerNotFound as e:
            log.debug(str(e))
            return await ctx.send(
                "The specified profile could not be found."
            )

        try:
            player = await self._choose_player(ctx, players)
        except errors.NoChoiceError as e:
            log.debug(str(e))
            return await ctx.send(
                "You didn't choose profile you want to connect."
            )

        await self.config.user(ctx.author).platform.set(player.platform.name)
        await self.config.user(ctx.author).player_id.set(player.player_id)

        await ctx.send(
            "You successfully connected your {} account with Discord!"
            .format(player.platform)
        )
