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

import asyncio
import contextlib
import functools
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Mapping,
    Tuple,
    TypedDict,
    TypeVar,
    cast,
)

import discord
import rlapi
from PIL import ImageFont
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands import NoParseOptional as Optional
from redbot.core.config import Config
from redbot.core.data_manager import bundled_data_path, cog_data_path
from redbot.core.utils.chat_formatting import bold, inline
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate
from rlapi.ext.tier_breakdown.rlstatsnet import get_tier_breakdown

from . import errors
from .abc import CogAndABCMeta
from .figures import Point
from .image import CoordsInfo, RLStatsImageTemplate
from .settings import SettingsMixin

log = logging.getLogger("red.jackcogs.rlstats")

T = TypeVar("T")
RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]


SUPPORTED_PLATFORMS = """Supported platforms:
- Steam - use steamID64, customURL or full URL to profile
- PlayStation 4 - use PSN ID
- Xbox One - use Xbox Gamertag
- Epic Games - use Epic Account ID (https://epicgames.com/help/c74/c79/a3659)
- Nintendo Switch - use Nintendo Network ID"""

RLSTATS_DOCS = f"""
Show Rocket League stats in {{mode}} playlists for you or given player.

{SUPPORTED_PLATFORMS}
If the user connected their game profile with `[p]rlconnect`,
you can also use their Discord tag to show their stats.
"""


class ClientCredentials(TypedDict):
    client_id: str
    client_secret: str


class RLStats(SettingsMixin, commands.Cog, metaclass=CogAndABCMeta):
    """Get your Rocket League stats with a single command!"""

    TIER_BREAKDOWN_EXPIRY_TIME = 3600.0 * 24
    RANK_SIZE = (179, 179)
    TIER_SIZE = (49, 49)
    OFFSETS = {
        # competitive
        rlapi.PlaylistKey.solo_duel: (0, 0),
        rlapi.PlaylistKey.doubles: (960, 0),
        rlapi.PlaylistKey.tournaments: (0, 383),
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
        "rank_image": CoordsInfo(Point(242, 337), None),
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
        7: "#ffffff",
    }

    def __init__(self, bot: Red) -> None:
        super().__init__()
        self.bot = bot
        self.loop: asyncio.AbstractEventLoop = bot.loop
        self._executor = ThreadPoolExecutor()
        self.config = Config.get_conf(
            self, identifier=6672039729, force_registration=True
        )
        self.config.register_global(
            tier_breakdown={},
            breakdown_updated_at=0.0,
            competitive_overlay=40,
            extramodes_overlay=70,
        )
        self.config.register_user(player_id=None, platform=None)

        self.breakdown_lock = asyncio.Lock()
        self.breakdown_updated_at = 0.0
        self.rlapi_client: rlapi.Client  # assigned in cog_load()
        self.bundled_data_path = bundled_data_path(self)
        self.cog_data_path = cog_data_path(self)
        self._prepare_templates()

    def _prepare_templates(self) -> None:
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

    async def cog_load(self) -> None:
        client_credentials = await self._get_client_credentials()
        self.rlapi_client = rlapi.Client(**client_credentials)
        tier_breakdown = self._convert_numbers_in_breakdown(
            await self.config.tier_breakdown()
        )
        self.rlapi_client.tier_breakdown = tier_breakdown
        self.breakdown_updated_at = await self.config.breakdown_updated_at()
        self.extramodes_template.bg_overlay = await self.config.extramodes_overlay()
        self.competitive_template.bg_overlay = await self.config.competitive_overlay()

    async def cog_unload(self) -> None:
        self.rlapi_client.destroy()

    async def red_get_data_for_user(self, *, user_id: int) -> Dict[str, BytesIO]:
        try:
            player_id, platform = await self._get_player_data_by_user_id(user_id)
        except errors.PlayerDataNotFound:
            return {}
        contents = (
            f"Rocket League game account for Discord user with ID {user_id}:\n"
            f"- Platform: {platform}\n"
            f"- Player ID: {player_id}\n"
        )
        return {"user_data.txt": BytesIO(contents.encode())}

    async def red_delete_data_for_user(
        self, *, requester: RequestType, user_id: int
    ) -> None:
        await self.config.user_from_id(user_id).clear()

    async def _run_in_executor(
        self, func: Callable[..., T], *args: Any, **kwargs: Any
    ) -> T:
        return await self.loop.run_in_executor(
            self._executor, functools.partial(func, *args, **kwargs)
        )

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

    async def _get_client_credentials(
        self, api_tokens: Optional[Mapping[str, str]] = None
    ) -> ClientCredentials:
        if api_tokens is None:
            api_tokens = await self.bot.get_shared_api_tokens("rocket_league")
        client_credentials: ClientCredentials = {
            "client_id": api_tokens.get("client_id", ""),
            "client_secret": api_tokens.get("client_secret", ""),
        }
        return client_credentials

    async def _check_client_credentials(self, ctx: commands.Context) -> bool:
        if not (self.rlapi_client._client_id and self.rlapi_client._client_secret):
            if await self.bot.is_owner(ctx.author):
                await ctx.send(
                    "This cog wasn't configured properly."
                    " You need to set a Client ID and Secret first, look at"
                    f" {inline(f'{ctx.clean_prefix}rlset credentials')}"
                    " for instructions."
                )
            else:
                await ctx.send("The bot owner didn't configure this cog properly.")
            return False
        return True

    async def _maybe_update_tier_breakdown(self) -> None:
        async with self.breakdown_lock:
            now = time.time()
            if self.breakdown_updated_at + self.TIER_BREAKDOWN_EXPIRY_TIME > now:
                return

            try:
                tier_breakdown = await get_tier_breakdown(self.rlapi_client)
            except rlapi.HTTPException as e:
                log.warning("Could not download tier breakdown.", exc_info=e)
            except ValueError as e:
                log.warning("Could not parse downloaded tier breakdown.", exc_info=e)
            else:
                self.rlapi_client.tier_breakdown = tier_breakdown
                await self.config.tier_breakdown.set(tier_breakdown)
            finally:
                self.breakdown_updated_at = now
                await self.config.breakdown_updated_at.set(now)

    async def _get_player_data_by_user_id(
        self, user_id: int
    ) -> Tuple[str, rlapi.Platform]:
        user_data = await self.config.user_from_id(user_id).all()
        player_id, platform = user_data["player_id"], user_data["platform"]
        if player_id is not None:
            return (player_id, rlapi.Platform[platform])
        raise errors.PlayerDataNotFound(
            f"Couldn't find player data for discord user with ID {user_id}"
        )

    async def _get_player_data_by_user(
        self, user: discord.abc.User
    ) -> Tuple[str, rlapi.Platform]:
        return await self._get_player_data_by_user_id(user.id)

    async def _get_players(
        self, player_ids: List[Tuple[str, Optional[rlapi.Platform]]]
    ) -> Tuple[rlapi.Player, ...]:
        players: List[rlapi.Player] = []
        for player_id, platform in player_ids:
            with contextlib.suppress(rlapi.PlayerNotFound):
                players += await self.rlapi_client.get_player(player_id, platform)
        if not players:
            raise rlapi.PlayerNotFound
        # using dict.fromkeys() to make duplicates go away
        return tuple(dict.fromkeys(players))

    async def _maybe_get_players(
        self,
        ctx: commands.Context,
        player_ids: List[Tuple[str, Optional[rlapi.Platform]]],
    ) -> Optional[Tuple[rlapi.Player, ...]]:
        try:
            players = await self._get_players(player_ids)
        except rlapi.Unauthorized as e:
            log.error(str(e))
            if await self.bot.is_owner(ctx.author):
                await ctx.send(
                    "Set client credentials are invalid."
                    f" Use {inline(f'{ctx.clean_prefix}rlset credentials')}"
                    " to update them."
                )
            else:
                await ctx.send("The bot owner didn't configure this cog properly.")
        except rlapi.HTTPException as e:
            log.error(str(e))
            if e.status >= 500:
                await ctx.send(
                    "Rocket League API experiences some issues right now."
                    " Try again later."
                )
            else:
                await ctx.send(
                    "Rocket League API can't process this request."
                    " If this keeps happening, inform bot's owner about this error."
                )
        except rlapi.PlayerNotFound as e:
            log.debug(str(e))
            await ctx.send("The specified profile could not be found.")
        else:
            return players

        return None

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
            pred = ReactionPredicate.with_emojis(emojis, msg, ctx.author)

            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=25)
            except asyncio.TimeoutError:
                raise errors.NoChoiceError("User didn't choose a profile to check.")
            finally:
                await msg.delete()

            result = cast(int, pred.result)
            return players[result]
        return players[0]

    def _generate_image(
        self,
        template: RLStatsImageTemplate,
        playlists: Tuple[rlapi.PlaylistKey, ...],
        player: rlapi.Player,
    ) -> BytesIO:
        result = template.generate_image(player, playlists)
        fp = BytesIO()
        result.thumbnail((960, 540))
        result.save(fp, "PNG")
        fp.seek(0)
        return fp

    # geninfo-ignore: missing-docstring
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    @commands.cooldown(rate=3, per=5, type=commands.BucketType.user)
    @commands.command()
    async def rlstats(
        self, ctx: commands.Context, *, player_id: Optional[str] = None
    ) -> None:
        playlists = (
            rlapi.PlaylistKey.solo_duel,
            rlapi.PlaylistKey.doubles,
            rlapi.PlaylistKey.tournaments,
            rlapi.PlaylistKey.standard,
        )
        await self._rlstats_logic(ctx, self.competitive_template, playlists, player_id)

    rlstats.callback.__doc__ = RLSTATS_DOCS.format(mode="competitive")

    # geninfo-ignore: missing-docstring
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    @commands.cooldown(rate=3, per=5, type=commands.BucketType.user)
    @commands.command()
    async def rlsports(
        self, ctx: commands.Context, *, player_id: Optional[str] = None
    ) -> None:
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
            if not await self._check_client_credentials(ctx):
                return
            await self._maybe_update_tier_breakdown()

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
                        f" {inline(f'{ctx.clean_prefix}rlstats <player_id>')}"
                        " or connect your account using command:"
                        f" {inline(f'{ctx.clean_prefix}rlconnect <player_id>')}"
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

            players = await self._maybe_get_players(ctx, player_ids)
            if players is None:
                return

            try:
                player = await self._choose_player(ctx, players)
            except errors.NoChoiceError as e:
                log.debug(e)
                await ctx.send(
                    "You didn't select a profile that you would like to check."
                )
                return

            # TODO: This should probably be handled in rlapi module
            # be careful when touching this part,
            # we rely on `player.get_playlist` not returning None in .image
            for playlist_key in playlists:
                if playlist_key not in player.playlists:
                    player.add_playlist({"playlist": playlist_key.value})

            # be extra careful when changing this (mypy won't type check this)
            fp = await self._run_in_executor(
                self._generate_image, template, playlists, player
            )
        if discord_user is not None and player.player_id == player_ids[0][0]:
            account_string = (
                f"connected {str(player.platform)} account of {bold(str(discord_user))}"
            )
        else:
            assert player.user_name is not None, "incorrect typing upstream"
            account_string = f"{str(player.platform)} account: {bold(player.user_name)}"
        await ctx.send(
            (
                f"Rocket League Stats for {account_string}\n"
                "*(arrows show amount of points for division down/up)*"
            ),
            file=discord.File(fp, f"{player.player_id}_profile.png"),
        )

    @commands.command()
    async def rlconnect(self, ctx: commands.Context, *, player_id: str) -> None:
        """Connect game profile with your Discord account."""
        async with ctx.typing():
            if not await self._check_client_credentials(ctx):
                return

            players = await self._maybe_get_players(ctx, [(player_id, None)])
            if players is None:
                return

            try:
                player = await self._choose_player(ctx, players)
            except errors.NoChoiceError as e:
                log.debug(str(e))
                await ctx.send(
                    "You didn't select a profile that you would like to connect."
                )
                return

            await self.config.user(ctx.author).platform.set(player.platform.name)
            await self.config.user(ctx.author).player_id.set(player.player_id)

        await ctx.send(
            f"You successfully connected your {player.platform} account with Discord!"
        )

    rlconnect.callback.__doc__ += f"\n\n{SUPPORTED_PLATFORMS}"

    @commands.command()
    async def rldisconnect(self, ctx: commands.Context) -> None:
        """
        Disconnect the game profile associated with
        your Discord account from RLStats cog.
        """
        await self.config.user(ctx.author).clear()
        await ctx.send("Your game account was successfully disconnected from Discord!")

    @commands.Cog.listener()
    async def on_red_api_tokens_update(
        self, service_name: str, api_tokens: Mapping[str, str]
    ) -> None:
        if service_name != "rocket_league":
            return

        client_credentials = await self._get_client_credentials(api_tokens)
        self.rlapi_client.update_client_credentials(**client_credentials)
