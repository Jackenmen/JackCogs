import asyncio
import contextlib
import logging
from io import BytesIO
from typing import List, Tuple, Optional, Iterable

import discord
from redbot.core import commands, checks
from redbot.core.config import Config
from redbot.core.utils.predicates import ReactionPredicate
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.data_manager import bundled_data_path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise RuntimeError("Can't load pillow. Do 'pip3 install pillow'.")

from . import rlapi
from .figures import Point, Rectangle
from . import errors

log = logging.getLogger('redbot.rlstats')


class RLStats(commands.Cog):
    """Get your Rocket League stats with a single command!"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6672039729,
                                      force_registration=True)
        self.config.register_global(tier_breakdown={})
        self.config.register_user(player_id=None, platform=None)
        self.rlapi_client = None
        self.size = (1920, 1080)
        self.data_path = bundled_data_path(self)
        self.fonts = {
            'RobotoCondensedBold90': ImageFont.truetype(
                str(self.data_path / "fonts/RobotoCondensedBold.ttf"), 90),
            'RobotoBold45': ImageFont.truetype(
                str(self.data_path / "fonts/RobotoBold.ttf"), 45),
            'RobotoLight45': ImageFont.truetype(
                str(self.data_path / "fonts/RobotoLight.ttf"), 45),
            'RobotoRegular74': ImageFont.truetype(
                str(self.data_path / "fonts/RobotoRegular.ttf"), 74)
        }
        self.offsets = {
            rlapi.PlaylistKey.SOLO_DUEL: (0, 0),
            rlapi.PlaylistKey.DOUBLES: (960, 0),
            rlapi.PlaylistKey.SOLO_STANDARD: (0, 383),
            rlapi.PlaylistKey.STANDARD: (960, 383)
        }
        self.coords = {
            'username': Point(960, 71),
            'playlist_name': Point(243, 197),
            'rank_image': Point(153, 248),
            'rank_text': Point(242, 453),  # center of rank text
            'matches_played': Point(822, 160),
            'win_streak': Point(492, 216),
            'skill': Point(729, 272),
            'gain': Point(715, 328),
            'div_down': Point(552, 384),
            'div_up': Point(727, 384),
            'tier_down': Point(492, 446),
            'tier_up': Point(667, 446),
            'rewards': Point(914, 921)
        }
        self.rank_size = (179, 179)
        self.tier_size = (49, 49)

    async def initialize(self):
        tier_breakdown = self.config.tier_breakdown
        self.rlapi_client = rlapi.Client(
            await self._get_token(),
            loop=self.bot.loop,
            tier_breakdown=self._convert_numbers_in_breakdown(await tier_breakdown())
        )
        await self.rlapi_client.setup
        await tier_breakdown.set(self.rlapi_client.tier_breakdown)

    def __unload(self):
        self.rlapi_client.destroy()

    __del__ = __unload

    def _convert_numbers_in_breakdown(self, d: dict, curr_lvl: int = 0):
        """Converts (recursively) dictionary's keys with numbers to integers"""
        new = {}
        func = self._convert_numbers_in_breakdown if curr_lvl < 2 else lambda v, _: v
        for k, v in d.items():
            v = func(v, curr_lvl+1)
            new[int(k)] = v
        return new

    def _get_coords(self, playlist_id, coords_name):
        """Gets coords for given element in chosen playlist"""
        coords = self.coords[coords_name]
        offset = self.offsets[playlist_id]
        return coords + offset

    async def _get_token(self):
        rocket_league = await self.bot.db.api_tokens.get_raw(
            "rocket_league", default={"user_token": ""}
        )
        return rocket_league.get('user_token', "")

    @checks.is_owner()
    @commands.group(name="rlset")
    async def rlset(self, ctx):
        """RLStats configuration options."""

    @checks.is_owner()
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
        """Checks for your or given player's Rocket League stats"""
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
                await ctx.send((
                    "Your game account is not connected with Discord. "
                    "If you want to get stats, "
                    "either give your player ID after a command: "
                    "`{0}rlstats <player_id>`"
                    " or connect your account using command: "
                    "`{0}rlconnect <player_id>`"
                ).format(ctx.prefix))
                return
        else:
            try:
                user = await commands.MemberConverter().convert(ctx, player_id)
            except commands.BadArgument:
                pass
            else:
                with contextlib.suppress(errors.PlayerDataNotFound):
                    player_ids.append(await self._get_player_data_by_user(user))
            player_ids.append((player_id, None))

        playlists = [
            rlapi.PlaylistKey.SOLO_DUEL,
            rlapi.PlaylistKey.DOUBLES,
            rlapi.PlaylistKey.SOLO_STANDARD,
            rlapi.PlaylistKey.STANDARD
        ]

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

        for playlist_key in playlists:
            if playlist_key not in player.playlists:
                player.add_playlist({'playlist': playlist_key})

        result = Image.open(self.data_path / 'rank_bg.png').convert('RGBA')
        process = Image.new('RGBA', self.size)
        draw = ImageDraw.Draw(process)

        # Draw - username
        w, h = self.fonts["RobotoCondensedBold90"].getsize(player.user_name)
        coords = self.coords['username'] - (w/2, h/2)
        draw.text(coords, player.user_name,
                  font=self.fonts["RobotoCondensedBold90"], fill="white")

        # Draw - rank details
        for playlist_key in playlists:
            # Draw - playlist name
            w, h = self.fonts["RobotoRegular74"].getsize(playlist_key.friendly_name)
            coords = self._get_coords(playlist_key, 'playlist_name')
            coords = coords - (w/2, h/2)
            draw.text(
                coords, playlist_key.friendly_name,
                font=self.fonts["RobotoRegular74"], fill="white"
            )

            # Draw - rank image
            playlist = player.get_playlist(playlist_key)
            temp = Image.new('RGBA', self.size)
            temp_image = Image.open(
                self.data_path / 'images/ranks/{}.png'.format(playlist.tier)
            ).convert('RGBA')
            temp_image.thumbnail(self.rank_size, Image.ANTIALIAS)
            coords = self._get_coords(playlist_key, 'rank_image')
            temp.paste(temp_image, Rectangle(coords, temp_image.size))
            process = Image.alpha_composite(process, temp)
            draw = ImageDraw.Draw(process)

            # Draw - rank name (e.g. Diamond 3 Div 1)

            w, h = self.fonts["RobotoLight45"].getsize(str(playlist))
            coords = self._get_coords(playlist_key, 'rank_text')
            coords = coords - (w/2, h/2)
            draw.text(
                coords, str(playlist),
                font=self.fonts["RobotoLight45"], fill="white"
            )

            # Draw - matches played
            coords = self._get_coords(playlist_key, 'matches_played')
            draw.text(
                coords, str(playlist.matches_played),
                font=self.fonts["RobotoBold45"], fill="white"
            )

            # Draw - Win/Losing Streak
            if playlist.win_streak < 0:
                text = "Losing Streak:"
            else:
                text = "Win Streak:"
            w, h = self.fonts["RobotoLight45"].getsize(text)
            coords_text = self._get_coords(playlist_key, 'win_streak')
            coords_amount = coords_text + (11+w, 0)
            # Draw - "Win Streak" or "Losing Streak"
            draw.text(coords_text, text, font=self.fonts["RobotoLight45"], fill="white")
            # Draw - amount of won/lost games
            draw.text(
                coords_amount, str(playlist.win_streak),
                font=self.fonts["RobotoBold45"], fill="white"
            )

            # Draw - Skill Rating
            coords = self._get_coords(playlist_key, 'skill')
            draw.text(
                coords, str(playlist.skill),
                font=self.fonts["RobotoBold45"], fill="white"
            )

            # Draw - Gain/Loss
            # TODO: rltracker rewrite needed to support this
            gain = 0

            coords = self._get_coords(playlist_key, 'gain')
            if gain == 0:
                draw.text(coords, "N/A", font=self.fonts["RobotoBold45"], fill="white")
            else:
                draw.text(
                    coords, str(round(gain, 3)),
                    font=self.fonts["RobotoBold45"], fill="white"
                )

            # Draw - Tier and division estimates
            # Draw - Division Down
            coords = self._get_coords(playlist_key, 'div_down')
            if playlist.tier_estimates.div_down is None:
                div_down = 'N/A'
            else:
                div_down = '{0:+d}'.format(playlist.tier_estimates.div_down)
            draw.text(coords, div_down, font=self.fonts["RobotoBold45"], fill="white")

            # Draw - Tier Down
            # Icon
            tier = playlist.tier_estimates.tier
            tier_down = self.data_path / 'images/ranks/{}.png'.format(
                tier-1 if tier > 0 else 0
            )
            tier_down_temp = Image.new('RGBA', self.size)
            tier_down_image = Image.open(tier_down).convert('RGBA')
            tier_down_image.thumbnail(self.tier_size, Image.ANTIALIAS)
            coords_image = self._get_coords(playlist_key, 'tier_down')
            tier_down_temp.paste(
                tier_down_image, Rectangle(coords_image, tier_down_image.size)
            )
            process = Image.alpha_composite(process, tier_down_temp)
            draw = ImageDraw.Draw(process)
            # Points
            if playlist.tier_estimates.tier_down is None:
                tier_down = 'N/A'
            else:
                tier_down = '{0:+d}'.format(playlist.tier_estimates.tier_down)
            coords_text = coords_image + (self.tier_size[0]+11, -5)
            draw.text(
                coords_text, tier_down,
                font=self.fonts["RobotoBold45"], fill="white"
            )

            # Draw - Division Up
            coords = self._get_coords(playlist_key, 'div_up')
            if playlist.tier_estimates.div_up is None:
                div_up = 'N/A'
            else:
                div_up = '{0:+d}'.format(playlist.tier_estimates.div_up)
            draw.text(coords, div_up, font=self.fonts["RobotoBold45"], fill="white")

            # Draw - Tier Up
            # Icon
            tier = playlist.tier_estimates.tier
            tier_up = self.data_path / 'images/ranks/{}.png'.format(
                tier+1 if 0 < tier < playlist.tier_max else 0
            )
            tier_up_temp = Image.new('RGBA', self.size)
            tier_up_image = Image.open(tier_up).convert('RGBA')
            tier_up_image.thumbnail(self.tier_size, Image.ANTIALIAS)
            coords_image = self._get_coords(playlist_key, 'tier_up')
            tier_up_temp.paste(
                tier_up_image, Rectangle(coords_image, tier_up_image.size)
            )
            process = Image.alpha_composite(process, tier_up_temp)
            draw = ImageDraw.Draw(process)
            # Points
            coords_text = coords_image + (self.tier_size[0]+11, -5)
            if playlist.tier_estimates.tier_up is None:
                tier_up = 'N/A'
            else:
                tier_up = '{0:+d}'.format(playlist.tier_estimates.tier_up)
            draw.text(
                coords_text, tier_up,
                font=self.fonts["RobotoBold45"], fill="white"
            )

        # Season Reward Level
        rewards = player.season_rewards

        reward_temp = Image.new('RGBA', self.size)
        reward_image = Image.open(
            self.data_path / 'images/rewards/{:d}_{:d}.png'.format(
                rewards.level, rewards.reward_ready
            )
        ).convert('RGBA')
        reward_temp.paste(reward_image, (150, 886))
        process = Image.alpha_composite(process, reward_temp)
        draw = ImageDraw.Draw(process)
        # Season Reward Bars
        if player.season_rewards.level != 7:
            reward_bars_win_image = Image.open(
                self.data_path / 'images/rewards/bars/Bar_{:d}_Win.png'
                .format(rewards.level)
            ).convert('RGBA')
            if player.season_rewards.reward_ready:
                reward_bars_nowin_image = Image.open(
                    self.data_path / 'images/rewards/bars/Bar_{:d}_NoWin.png'
                    .format(rewards.level)
                ).convert('RGBA')
            else:
                reward_bars_nowin_image = Image.open(
                    self.data_path / 'images/rewards/bars/Bar_Red.png'
                ).convert('RGBA')
            for win in range(0, 10):
                reward_bars_temp = Image.new('RGBA', self.size)
                coords = self.coords['rewards'] + (win*83, 0)
                if rewards.wins > win:
                    reward_bars_temp.paste(
                        reward_bars_win_image,
                        Rectangle(coords, reward_bars_win_image.size)
                    )
                else:
                    reward_bars_temp.paste(
                        reward_bars_nowin_image,
                        Rectangle(coords, reward_bars_nowin_image.size)
                    )
                process = Image.alpha_composite(process, reward_bars_temp)
                draw = ImageDraw.Draw(process)

        # save result
        result = Image.alpha_composite(result, process)
        fp = BytesIO()
        result.save(fp, 'PNG', quality=100)
        fp.seek(0)
        await ctx.send(
            (
                'Rocket League Stats for **{}** '
                '*(arrows show amount of points for division down/up)*'
            ).format(player.user_name),
            file=discord.File(fp, '{}_profile.png'.format(player_id))
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

    @checks.is_owner()
    @rlset.command(name="updatebreakdown")
    async def updatebreakdown(self, ctx):
        """Update tier breakdown"""
        await ctx.send("Updating tier breakdown...")
        async with ctx.typing():
            await self.rlapi_client.update_tier_breakdown()
            await self.config.tier_breakdown.set(self.rlapi_client.tier_breakdown)
        await ctx.send("Tier breakdown updated.")
