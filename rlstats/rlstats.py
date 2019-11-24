import asyncio
import contextlib
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, cast

import discord
import rlapi
from redbot.core import checks, commands
from redbot.core.bot import Red
from redbot.core.config import Config, Value
from redbot.core.data_manager import bundled_data_path, cog_data_path
from redbot.core.utils.chat_formatting import bold, inline
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate
from rlapi.ext.tier_breakdown.trackernetwork import get_tier_breakdown

from . import errors
from .figures import Point
from .image import CoordsInfo, RLStatsImageTemplate

try:
    from PIL import Image, ImageFont
except ImportError:
    raise RuntimeError("Can't load pillow. Do 'pip3 install pillow'.")


log = logging.getLogger("red.jackcogs.rlstats")

T = TypeVar("T")


SUPPORTED_PLATFORMS = """Supported platforms:
- Steam - use steamID64, customURL or full URL to profile
- PlayStation 4 - use PSN ID
- Xbox One - use Xbox Gamertag"""

RLSTATS_DOCS = f"""Show Rocket League stats in {{mode}} playlists for you or given player.

{SUPPORTED_PLATFORMS}
If the user connected their game profile with `[p]rlconnect`,
you can also use their Discord tag to show their stats."""


class RLStats(commands.Cog):
    """Get your Rocket League stats with a single command!"""

    RANK_SIZE = (179, 179)
    TIER_SIZE = (49, 49)
    OFFSETS = {
        # competitive
        rlapi.PlaylistKey.solo_duel: (0, 0),
        rlapi.PlaylistKey.doubles: (960, 0),
        rlapi.PlaylistKey.solo_standard: (0, 383),
        rlapi.PlaylistKey.standard: (960, 383),
        # extra modes
        rlapi.PlaylistKey.hoops: (0, 0),
        rlapi.PlaylistKey.rumble: (960, 0),
        rlapi.PlaylistKey.dropshot: (0, 383),
        rlapi.PlaylistKey.snow_day: (960, 383),
    }
    COORDS = {
        "username": CoordsInfo(Point(960, 71), "RobotoCondensedBold90"),
        "platform": CoordsInfo(Point(976, 83), None),
        "playlist_name": CoordsInfo(Point(243, 197), "RobotoRegular74"),
        "rank_image": CoordsInfo(Point(153, 248), None),
        "rank_text": CoordsInfo(Point(242, 453), "RobotoLight45"),
        "matches_played": CoordsInfo(Point(822, 160), "RobotoBold45"),
        "win_streak_text": CoordsInfo(Point(492, 216), "RobotoLight45"),
        "win_streak_amount": CoordsInfo(Point(503, 216), "RobotoBold45"),
        "skill": CoordsInfo(Point(729, 272), "RobotoBold45"),
        "gain": CoordsInfo(Point(715, 328), "RobotoBold45"),
        "div_down": CoordsInfo(Point(552, 384), "RobotoBold45"),
        "div_up": CoordsInfo(Point(727, 384), "RobotoBold45"),
        "tier_down": CoordsInfo(Point(492, 446), "RobotoBold45"),
        "tier_up": CoordsInfo(Point(667, 446), "RobotoBold45"),
        "season_rewards_lvl": CoordsInfo(Point(150, 886), None),
        "season_rewards_bars": CoordsInfo(Point(831, 921), None),
        "season_rewards_wins_text": CoordsInfo(Point(1582, 956), None),
        "season_rewards_wins_max": CoordsInfo(Point(1658, 954), "ArimoRegular56"),
        "season_rewards_wins_amount": CoordsInfo(Point(1575, 954), "ArimoRegular56"),
    }
    SEASON_REWARDS_COLORS = {
        -1: "#fc3f3f",
        0: "#c18659",
        1: "#b6b7b8",
        2: "#cbb36b",
        3: "#c8dcdc",
        4: "#95d9d7",
        5: "#c1afda",
        6: "#d9caf0",
    }

    def __init__(self, bot: Red) -> None:
        super().__init__()
        self.bot = bot
        if hasattr(bot, "db"):
            # compatibility layer with Red 3.1.x
            async def get_shared_api_tokens(service_name: str) -> Dict[str, str]:
                tokens = await bot.db.api_tokens.get_raw(service_name, default={})
                # api_tokens spec defines it's a dict of strings
                return cast(Dict[str, str], tokens)

            self.get_shared_api_tokens = get_shared_api_tokens
        else:
            self.get_shared_api_tokens = bot.get_shared_api_tokens
        self.config = Config.get_conf(
            self, identifier=6672039729, force_registration=True
        )
        self.config.register_global(
            tier_breakdown={}, competitive_overlay=40, extramodes_overlay=70
        )
        self.config.register_user(player_id=None, platform=None)
        self.rlapi_client: rlapi.Client = None
        self.bundled_data_path = bundled_data_path(self)
        self.cog_data_path = cog_data_path(self)
        self.fonts = {
            "ArimoRegular56": ImageFont.truetype(
                str(self.bundled_data_path / "fonts/ArimoRegular.ttf"), 56
            ),
            "RobotoCondensedBold90": ImageFont.truetype(
                str(self.bundled_data_path / "fonts/RobotoCondensedBold.ttf"), 90
            ),
            "RobotoRegular74": ImageFont.truetype(
                str(self.bundled_data_path / "fonts/RobotoRegular.ttf"), 74
            ),
            "RobotoBold45": ImageFont.truetype(
                str(self.bundled_data_path / "fonts/RobotoBold.ttf"), 45
            ),
            "RobotoLight45": ImageFont.truetype(
                str(self.bundled_data_path / "fonts/RobotoLight.ttf"), 45
            ),
        }
        self.images = {
            "platform_image": str(self.bundled_data_path) + "/images/platforms/{}.png",
            "tier_image": str(self.bundled_data_path) + "/images/ranks/{}.png",
            "season_rewards_lvl": (
                str(self.bundled_data_path) + "/images/rewards/{:d}_{:d}.png"
            ),
            "season_rewards_bars_win": (
                str(self.bundled_data_path) + "/images/rewards/bars/Bar_{:d}_Win.png"
            ),
            "season_rewards_bars_nowin": (
                str(self.bundled_data_path) + "/images/rewards/bars/Bar_{:d}_NoWin.png"
            ),
            "season_rewards_bars_red": (
                str(self.bundled_data_path) + "/images/rewards/bars/Bar_Red.png"
            ),
            "season_rewards_wins_white": (
                str(self.bundled_data_path) + "/images/rewards/bars/GlobalWhite.png"
            ),
            "season_rewards_wins_red": (
                str(self.bundled_data_path) + "/images/rewards/bars/GlobalRed.png"
            ),
        }
        self.rank_base = self.bundled_data_path / "rank_base.png"
        bg_image = self.cog_data_path / "bgs/competitive.png"
        if not bg_image.is_file():
            bg_image = self.bundled_data_path / "bgs/competitive.png"
        self.competitive_template = RLStatsImageTemplate(
            rank_size=self.RANK_SIZE,
            tier_size=self.TIER_SIZE,
            offsets=self.OFFSETS,
            coords=self.COORDS,
            fonts=self.fonts,
            bg_image=bg_image,
            bg_overlay=40,
            rank_base=self.rank_base,
            images=self.images,
            season_rewards_colors=self.SEASON_REWARDS_COLORS,
        )
        bg_image = self.cog_data_path / "bgs/extramodes.png"
        if not bg_image.is_file():
            bg_image = self.bundled_data_path / "bgs/extramodes.png"
        self.extramodes_template = RLStatsImageTemplate(
            rank_size=self.RANK_SIZE,
            tier_size=self.TIER_SIZE,
            offsets=self.OFFSETS,
            coords=self.COORDS,
            fonts=self.fonts,
            bg_image=bg_image,
            bg_overlay=70,
            rank_base=self.rank_base,
            images=self.images,
            season_rewards_colors=self.SEASON_REWARDS_COLORS,
        )

    async def initialize(self) -> None:
        self.rlapi_client = rlapi.Client(await self._get_token(), loop=self.bot.loop)
        tier_breakdown = self._convert_numbers_in_breakdown(
            await self.config.tier_breakdown()
        )
        if not tier_breakdown:
            tier_breakdown = await get_tier_breakdown(self.rlapi_client)
            await self.config.tier_breakdown.set(tier_breakdown)
        self.rlapi_client.tier_breakdown = tier_breakdown
        self.extramodes_template.bg_overlay = await self.config.extramodes_overlay()
        self.competitive_template.bg_overlay = await self.config.competitive_overlay()

    def cog_unload(self) -> None:
        self.rlapi_client.destroy()

    __del__ = cog_unload

    def _convert_numbers_in_breakdown(
        self, d: Dict[str, Any], curr_lvl: int = 0
    ) -> Dict[int, Any]:
        """Converts (recursively) dictionary's keys with numbers to integers"""
        new = {}
        func: Callable[[Any, int], Any]
        if curr_lvl < 2:
            func = self._convert_numbers_in_breakdown
        else:
            # just return value on lvl 2 (should be list)
            def func(v: T, _: int) -> T:
                return v

        for k, v in d.items():
            v = func(v, curr_lvl + 1)
            new[int(k)] = v
        return new

    async def _get_token(self) -> str:
        rocket_league = await self.get_shared_api_tokens("rocket_league")
        return rocket_league.get("user_token", "")

    @checks.is_owner()
    @commands.group(name="rlset")
    async def rlset(self, ctx: commands.Context) -> None:
        """RLStats configuration options."""

    @rlset.command()
    async def token(self, ctx: commands.Context) -> None:
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
    async def updatebreakdown(self, ctx: commands.Context) -> None:
        """Update tier breakdown."""
        await ctx.send("Updating tier breakdown...")
        async with ctx.typing():
            tier_breakdown = await get_tier_breakdown(self.rlapi_client)
            await self.config.tier_breakdown.set(tier_breakdown)
            self.rlapi_client.tier_breakdown = tier_breakdown
        await ctx.send("Tier breakdown updated.")

    @rlset.group(name="image")
    async def rlset_bgimage(self, ctx: commands.Context) -> None:
        """Set background for stats image."""

    @rlset_bgimage.group(name="extramodes")
    async def rlset_bgimage_extramodes(self, ctx: commands.Context) -> None:
        """Options for background for extra modes stats image."""

    @rlset_bgimage_extramodes.command("set")
    async def rlset_bgimage_extramodes_set(self, ctx: commands.Context) -> None:
        """
        Set background for extra modes stats image.

        Use `[p]rlset bgimage extramodes reset` to reset to default.
        """
        await self._rlset_bgimage_set(
            ctx, self.cog_data_path / "bgs/extramodes.png", self.extramodes_template
        )

    @rlset_bgimage_extramodes.command("reset")
    async def rlset_bgimage_extramodes_reset(self, ctx: commands.Context) -> None:
        """Reset background for extra modes stats image to default."""
        await self._rlset_bgimage_reset(
            ctx,
            "extra modes",
            self.cog_data_path / "bgs/extramodes.png",
            self.bundled_data_path / "bgs/extramodes.png",
            self.extramodes_template,
        )

    @rlset_bgimage_extramodes.command("overlay")
    async def rlset_bgimage_extramodes_overlay(
        self, ctx: commands.Context, percentage: int = None
    ) -> None:
        """
        Set overlay percentage for extra modes stats image.

        Leave empty to reset to default (70)
        """
        await self._rlset_bgimage_overlay(
            ctx,
            percentage,
            "extra modes",
            self.config.extramodes_overlay,
            self.extramodes_template,
        )

    @rlset_bgimage.group(name="competitive")
    async def rlset_bgimage_competitive(self, ctx: commands.Context) -> None:
        """Options for background for competitive stats image."""

    @rlset_bgimage_competitive.command("set")
    async def rlset_bgimage_competitive_set(self, ctx: commands.Context) -> None:
        """
        Set background for competitive stats image.

        Use `[p]rlset bgimage competitive reset` to reset to default.
        """
        await self._rlset_bgimage_set(
            ctx, self.cog_data_path / "bgs/competitive.png", self.competitive_template
        )

    @rlset_bgimage_competitive.command("reset")
    async def rlset_bgimage_competitive_reset(self, ctx: commands.Context) -> None:
        """Reset background for competitive stats image to default."""
        await self._rlset_bgimage_reset(
            ctx,
            "competitive",
            self.cog_data_path / "bgs/competitive.png",
            self.bundled_data_path / "bgs/competitive.png",
            self.competitive_template,
        )

    @rlset_bgimage_competitive.command("overlay")
    async def rlset_bgimage_competitive_overlay(
        self, ctx: commands.Context, percentage: int = None
    ) -> None:
        """
        Set overlay percentage for competitive stats image.

        Leave empty to reset to default (40)
        """
        await self._rlset_bgimage_overlay(
            ctx,
            percentage,
            "competitive",
            self.config.competitive_overlay,
            self.competitive_template,
        )

    async def _rlset_bgimage_set(
        self, ctx: commands.Context, filename: Path, template: RLStatsImageTemplate
    ) -> None:
        if not ctx.message.attachments:
            await ctx.send("You have to send background image.")
            return
        if len(ctx.message.attachments) > 1:
            await ctx.send("You can send only one attachment.")
            return
        async with ctx.typing():
            a = ctx.message.attachments[0]
            fp = BytesIO()
            await a.save(fp)
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            try:
                im = Image.open(fp)
            except IOError:
                await ctx.send("Attachment couldn't be open.")
                return
            try:
                im.convert("RGBA").save(filename, "PNG")
            except FileNotFoundError:
                await ctx.send("Attachment couldn't be saved.")
                return
            template.bg_image = filename
        await ctx.send("Background image was successfully set.")

    async def _rlset_bgimage_reset(
        self,
        ctx: commands.Context,
        mode: str,
        custom_filename: Path,
        default_filename: Path,
        template: RLStatsImageTemplate,
    ) -> None:
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

    async def _rlset_bgimage_overlay(
        self,
        ctx: commands.Context,
        percentage: Optional[int],
        mode: str,
        value_obj: Value,
        template: RLStatsImageTemplate,
    ) -> None:
        if percentage is None:
            await value_obj.clear()
            template.bg_overlay = await value_obj()
            await ctx.send(f"Overlay percentage for {mode} stats image reset.")
            return
        if not 0 <= percentage <= 100:
            await ctx.send("Percentage value has to be in range 0-100.")
            return
        await value_obj.set(percentage)
        template.bg_overlay = percentage
        await ctx.send(f"Overlay percentage for {mode} stats set to {percentage}%")

    async def _get_player_data_by_user(
        self, user: discord.abc.User
    ) -> Tuple[str, rlapi.Platform]:
        """nwm"""
        user_data = await self.config.user(user).all()
        player_id, platform = user_data["player_id"], user_data["platform"]
        if player_id is not None:
            return (player_id, rlapi.Platform[platform])
        raise errors.PlayerDataNotFound(
            f"Couldn't find player data for discord user with ID {user.id}"
        )

    async def _get_players(
        self, player_ids: List[Tuple[str, Optional[rlapi.Platform]]]
    ) -> Tuple[rlapi.Player, ...]:
        players: List[rlapi.Player] = []
        for player_id, platform in player_ids:
            with contextlib.suppress(rlapi.PlayerNotFound):
                players += await self.rlapi_client.get_player(player_id, platform)
        if not players:
            raise rlapi.PlayerNotFound
        return tuple(players)

    async def _choose_player(
        self, ctx: commands.Context, players: Tuple[rlapi.Player, ...]
    ) -> rlapi.Player:
        players_len = len(players)
        if players_len > 1:
            description = ""
            for idx, player in enumerate(players, 1):
                description += "\n{}. {} account with username: {}".format(
                    idx, player.platform, player.user_name
                )
            msg = await ctx.send(
                embed=discord.Embed(
                    title="There are multiple accounts with provided name:",
                    description=description,
                )
            )

            emojis = ReactionPredicate.NUMBER_EMOJIS[1 : players_len + 1]
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

    @commands.bot_has_permissions(attach_files=True)
    @commands.command()
    async def rlstats(self, ctx: commands.Context, *, player_id: str = None) -> None:
        playlists = (
            rlapi.PlaylistKey.solo_duel,
            rlapi.PlaylistKey.doubles,
            rlapi.PlaylistKey.solo_standard,
            rlapi.PlaylistKey.standard,
        )
        await self._rlstats_logic(ctx, self.competitive_template, playlists, player_id)

    rlstats.callback.__doc__ = RLSTATS_DOCS.format(mode="competitive")

    @commands.bot_has_permissions(attach_files=True)
    @commands.command()
    async def rlsports(self, ctx: commands.Context, *, player_id: str = None) -> None:
        playlists = (
            rlapi.PlaylistKey.hoops,
            rlapi.PlaylistKey.rumble,
            rlapi.PlaylistKey.dropshot,
            rlapi.PlaylistKey.snow_day,
        )
        await self._rlstats_logic(ctx, self.extramodes_template, playlists, player_id)

    rlsports.callback.__doc__ = RLSTATS_DOCS.format(mode="extra modes")

    async def _rlstats_logic(
        self,
        ctx: commands.Context,
        template: RLStatsImageTemplate,
        playlists: Tuple[rlapi.PlaylistKey, ...],
        player_id: Optional[str],
    ) -> None:
        async with ctx.typing():
            token = await self._get_token()
            if not token:
                if self.bot.is_owner(ctx.author):
                    await ctx.send(
                        "This cog wasn't configured properly."
                        f" You can setup the cog using {inline(f'{ctx.prefix}rlset')}."
                    )
                else:
                    await ctx.send("The bot owner didn't configure this cog properly.")
                return
            self.rlapi_client.change_token(token)

            player_ids: List[Tuple[str, Optional[rlapi.Platform]]] = []
            discord_user = None
            if player_id is None:
                try:
                    player_ids.append(await self._get_player_data_by_user(ctx.author))
                    discord_user = ctx.author
                except errors.PlayerDataNotFound:
                    await ctx.send(
                        "Your game account is not connected with Discord."
                        " If you want to get stats,"
                        " either give your player ID after a command:"
                        f" `{ctx.prefix}rlstats <player_id>`"
                        " or connect your account using command:"
                        f" `{ctx.prefix}rlconnect <player_id>`"
                    )
                    return
            else:
                try:
                    discord_user = await commands.MemberConverter().convert(
                        ctx, player_id
                    )
                except commands.BadArgument:
                    pass
                else:
                    try:
                        player_ids.append(
                            await self._get_player_data_by_user(discord_user)
                        )
                    except errors.PlayerDataNotFound:
                        discord_user = None
                player_ids.append((player_id, None))

            try:
                players = await self._get_players(player_ids)
            except rlapi.Unauthorized as e:
                log.error(str(e))
                if self.bot.is_owner(ctx.author):
                    await ctx.send(
                        f"Set token is invalid. Use {inline(f'{ctx.prefix}rlset')}"
                        " to change the token."
                    )
                else:
                    await ctx.send("The bot owner didn't configure this cog properly.")
                return
            except rlapi.HTTPException as e:
                log.error(str(e))
                if e.status >= 500:
                    await ctx.send(
                        "Rocket League API experiences some issues right now."
                        " Try again later."
                    )
                    return
                await ctx.send(
                    "Rocket League API can't process this request."
                    " If this keeps happening, inform bot's owner about this error."
                )
                return
            except rlapi.PlayerNotFound as e:
                log.debug(str(e))
                await ctx.send("The specified profile could not be found.")
                return

            try:
                player = await self._choose_player(ctx, players)
            except errors.NoChoiceError as e:
                log.debug(e)
                await ctx.send("You didn't choose profile you want to check.")
                return

            # TODO: This should probably be handled in rlapi module
            for playlist_key in playlists:
                if playlist_key not in player.playlists:
                    player.add_playlist({"playlist": playlist_key.value})

            result = template.generate_image(player, playlists)
            fp = BytesIO()
            result.thumbnail((960, 540))
            result.save(fp, "PNG")
            fp.seek(0)
        if discord_user is not None and player.player_id == player_ids[0][0]:
            account_string = (
                f"connected {str(player.platform)} account of {bold(str(discord_user))}"
            )
        else:
            account_string = f"{str(player.platform)} account: {bold(player.user_name)}"
        await ctx.send(
            (
                f"Rocket League Stats for {account_string}\n"
                "*(arrows show amount of points for division down/up)*"
            ),
            file=discord.File(fp, f"{player.player_id}_profile.png"),
        )

    @commands.command()
    async def rlconnect(self, ctx: commands.Context, player_id: str) -> None:
        """Connect game profile with your Discord account."""
        async with ctx.typing():
            try:
                players = await self.rlapi_client.get_player(player_id)
            except rlapi.HTTPException as e:
                log.error(str(e))
                await ctx.send(
                    "Rocket League API experiences some issues right now."
                    " Try again later."
                )
                return
            except rlapi.PlayerNotFound as e:
                log.debug(str(e))
                await ctx.send("The specified profile could not be found.")
                return

            try:
                player = await self._choose_player(ctx, players)
            except errors.NoChoiceError as e:
                log.debug(str(e))
                await ctx.send("You didn't choose profile you want to connect.")
                return

            await self.config.user(ctx.author).platform.set(player.platform.name)
            await self.config.user(ctx.author).player_id.set(player.player_id)

        await ctx.send(
            f"You successfully connected your {player.platform} account with Discord!"
        )

    rlconnect.callback.__doc__ += f"\n\n{SUPPORTED_PLATFORMS}"
