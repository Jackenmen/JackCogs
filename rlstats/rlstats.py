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

import asyncio
import contextlib
import csv
import dataclasses
import enum
import functools
import hashlib
import itertools
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    TextIO,
    Tuple,
    TypedDict,
    TypeVar,
    Union,
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
from redbot.core.utils import can_user_send_messages_in
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
GUILD_SUBSCRIPTIONS = "GUILD_SUBSCRIPTIONS"
TRACKED_PLAYERS = "TRACKED_PLAYERS"
PlaylistChange = Tuple[Dict[str, Any], Dict[str, Any]]
PlaylistChangeSet = Dict[rlapi.PlaylistKey, PlaylistChange]
DEFAULT_TRACKER_INTERVAL = 180.0
PLAYLIST_HISTORY_V1_FIELDS = (
    # tracker-specific fields
    "updated_at",
    # API fields
    "tier",
    "division",
    "mu",
    "skill",
    "sigma",
    "win_streak",
    "matches_played",
    "lifetime_matches_played",
    "placement_matches_played",
)
REWARDS_HISTORY_V1_FIELDS = (
    # tracker-specific fields
    "updated_at",
    # API fields
    "level",
    "wins",
)


SUPPORTED_PLATFORMS = """Supported platforms:
- Steam - use steamID64, customURL or full URL to profile
- PlayStation - use PSN username (Online ID)\
 or [Account ID](https://psn.flipscreen.games)
- Xbox One - use Xbox Gamertag or [services ID (XUID)](https://www.cxkes.me/xbox/xuid)
- Epic Games - use Epic [Account ID](https://epicgames.com/help/c74/c79/a3659)\
 or Display Name
- Nintendo Switch - use Nintendo Nickname or your linked Epic account"""

RLSTATS_DOCS = f"""
Show Rocket League stats in {{mode}} playlists for you or given player.

{SUPPORTED_PLATFORMS}
If the user connected their game profile with `[p]rlconnect`,
you can also use their Discord tag to show their stats.
"""


class ClientCredentials(TypedDict):
    client_id: str
    client_secret: str


class LookupMethod(enum.Enum):
    id = "id"
    name = "name"


class GuildSubscriptionDeleteQuestionView(discord.ui.View):
    def __init__(
        self,
        *,
        parent: GuildSubscriptionView,
        author: discord.abc.User,
        original_interaction: discord.Interaction,
    ) -> None:
        super().__init__()
        self.parent = parent
        self.author = author
        self.original_interaction = original_interaction
        self.delete_interaction: Optional[discord.Interaction] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author.id != interaction.user.id:
            await interaction.response.send_message(
                "You cannot interact with this.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        print("GuildSubscriptionDeleteQuestionView timeout")
        await self.original_interaction.edit_original_response(
            content=self.parent.message_content, view=self.parent
        )

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def delete_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button[GuildSubscriptionDeleteQuestionView],
    ) -> None:
        self.stop()
        self.delete_interaction = interaction

    @discord.ui.button(label="Cancel")
    async def cancel_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button[GuildSubscriptionDeleteQuestionView],
    ) -> None:
        self.stop()
        await interaction.response.edit_message(
            content=self.parent.message_content, view=self.parent
        )


class GuildSubscriptionView(discord.ui.View):
    MAX_SELECT_OPTIONS = 25
    PER_PAGE_COUNT = MAX_SELECT_OPTIONS
    MAX_PAGE_COUNT = MAX_SELECT_OPTIONS

    def __init__(
        self,
        ctx: commands.GuildContext,
        cog: RLStats,
        guild_data: Dict[str, Dict[str, Dict[str, Any]]],
    ) -> None:
        super().__init__()
        self.ctx = ctx
        self.message_content = (
            "Select the channel and then the player that you want to unsubscribe."
        )
        self.message: Optional[discord.Message] = None
        self.cog = cog
        self.guild_data = guild_data
        self.page_count = min(
            len(guild_data) // self.PER_PAGE_COUNT + 1,
            self.MAX_PAGE_COUNT,
        )
        self.current_page = 0
        self.current_channel_id = ""
        self.change_page(0)
        if self.page_count < 2:
            self.remove_item(self.page_select)

    async def send(self) -> None:
        await self.change_channel("")
        self.message = await self.ctx.send(self.message_content, view=self)

    async def on_timeout(self) -> None:
        print("GuildSubscriptionView timeout")
        if self.message is None:
            return
        await self.message.edit(content="This message's view has expired.", view=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.ctx.author.id != interaction.user.id:
            await interaction.response.send_message(
                "You cannot interact with this.", ephemeral=True
            )
            return False
        return True

    def change_page(self, page_idx: int) -> None:
        self.current_page = page_idx
        start = page_idx * self.PER_PAGE_COUNT
        stop = start + self.PER_PAGE_COUNT
        self.channel_select.options.clear()
        for raw_channel_id, channel_data in itertools.islice(
            self.guild_data.items(),
            start,
            stop,
        ):
            channel = self.ctx.guild.get_channel_or_thread(int(raw_channel_id))
            if channel is None:
                continue
            if channel.type is discord.ChannelType.text:
                description = "text channel"
            elif channel.type is discord.ChannelType.voice:
                description = "voice channel"
            elif channel.type is discord.ChannelType.stage_voice:
                description = "stage channel"
            elif isinstance(channel, discord.Thread):
                description = "thread"
            else:
                description = "unknown channel type"

            player_count = sum(
                1
                for platform_data in channel_data.values()
                for _ in platform_data["ids"]
            )
            description = f"{description} ({player_count} players)"
            self.channel_select.options.append(
                discord.SelectOption(
                    label=channel.name,
                    description=description,
                    value=raw_channel_id,
                    default=raw_channel_id == self.current_channel_id,
                ),
            )

        for option_idx, option in enumerate(self.page_select.options):
            option.default = option_idx == page_idx

    def update_channel_select_default(self, channel_id: str) -> None:
        self.current_channel_id = channel_id
        for option in self.channel_select.options:
            option.default = option.value == channel_id

    async def change_channel(self, channel_id: str) -> None:
        self.update_channel_select_default(channel_id)
        self.player_select.placeholder = None
        if not channel_id:
            self.player_select.placeholder = "Select the channel first"
            self.player_select.options.clear()
            self.player_select.options.append(
                discord.SelectOption(label=self.player_select.placeholder)
            )
            self.player_select.disabled = True
            return
        self.player_select.disabled = False
        self.player_select.options.clear()
        for raw_platform, platform_data in self.guild_data[channel_id].items():
            platform = rlapi.Platform[raw_platform]
            for player_id in platform_data["ids"]:
                option = discord.SelectOption(
                    label="Unknown player",
                    description=f"Platform: {platform}; ID: {player_id}",
                    value=f"{raw_platform}_{player_id}",
                )
                try:
                    player = await self.cog.rlapi_client.get_player_by_id(
                        platform, player_id
                    )
                except rlapi.PlayerNotFound:
                    pass
                else:
                    option.label = player.user_name
                self.player_select.options.append(option)

    @discord.ui.select()
    async def channel_select(
        self,
        interaction: discord.Interaction,
        select: discord.ui.Select[GuildSubscriptionView],
    ) -> None:
        raw_channel_id = select.values[0]
        self.player_select.placeholder = "Loading..."
        self.player_select.disabled = True
        self.update_channel_select_default(raw_channel_id)
        await interaction.response.edit_message(view=self)
        await self.change_channel(raw_channel_id)
        await interaction.edit_original_response(view=self)

    @discord.ui.select(disabled=True)
    async def player_select(
        self,
        interaction: discord.Interaction,
        select: discord.ui.Select[GuildSubscriptionView],
    ) -> None:
        channel_id = int(self.current_channel_id)
        raw_platform, player_id = select.values[0].split("_", maxsplit=1)
        for idx, option in enumerate(self.player_select.options):
            if option.value == select.values[0]:
                deleted_option = option
                deleted_option_idx = idx
                break
        else:
            await interaction.response.edit_message(
                content=(
                    "Unexpected error occurred"
                    " and the selected player could not be deleted."
                ),
                view=None,
            )
            return

        confirm_view = GuildSubscriptionDeleteQuestionView(
            parent=self,
            original_interaction=interaction,
            author=self.ctx.author,
        )
        await interaction.response.edit_message(
            content=(
                "Are you sure that you want to unsubscribe to updates for"
                f" {deleted_option.label} ({deleted_option.description})?"
            ),
            view=confirm_view,
        )
        await confirm_view.wait()
        if not confirm_view.delete_interaction:
            return

        self.player_select.options.pop(deleted_option_idx)
        if self.player_select.options:
            channel_data = self.guild_data[self.current_channel_id]
            ids = channel_data[raw_platform]["ids"]
            while True:
                try:
                    ids.remove(player_id)
                except ValueError:
                    break
        else:
            del self.guild_data[self.current_channel_id]
            await self.change_channel("")
        self.change_page(self.current_page)

        if self.guild_data:
            await confirm_view.delete_interaction.response.edit_message(
                content=self.message_content, view=self
            )
        else:
            await confirm_view.delete_interaction.response.edit_message(
                content=(
                    "There are no more active profile update"
                    " subscriptions in this server."
                ),
                view=None,
            )

        await self._unsubscribe(channel_id, raw_platform, player_id)
        await confirm_view.delete_interaction.followup.send(
            "Unsubscribed the channel from profile updates for"
            f" {deleted_option.label} ({deleted_option.description})."
        )

    async def _unsubscribe(
        self, channel_id: int, raw_platform: str, player_id: str
    ) -> None:
        raw_channel_id = str(channel_id)
        async with self.cog.config.custom(
            GUILD_SUBSCRIPTIONS,
            str(self.ctx.guild.id),
        ).all() as guild_data:
            # remove player ID from guild subscriptions
            try:
                channel_data = guild_data[raw_channel_id]
            except KeyError:
                return
            platform_data = channel_data.get(raw_platform, {"ids": []})
            ids = platform_data["ids"]
            while True:
                try:
                    ids.remove(player_id)
                except ValueError:
                    break
            # cleanup empty structures
            if not ids:
                channel_data.pop(raw_platform, None)
            if not channel_data:
                del guild_data[raw_channel_id]

            # remove channel ID from tracked players
            scope = self.cog.config.custom(
                TRACKED_PLAYERS,
                raw_platform,
                player_id,
                str(self.ctx.guild.id),
            )
            async with scope.subscribed_channels() as subscribed_channels:
                while True:
                    try:
                        subscribed_channels.remove(channel_id)
                    except ValueError:
                        break
            # cleanup empty structure
            if not subscribed_channels:
                await scope.clear()

    @discord.ui.select()
    async def page_select(
        self,
        interaction: discord.Interaction,
        select: discord.ui.Select[GuildSubscriptionView],
    ) -> None:
        self.change_page(int(select.values[0]))
        await interaction.response.edit_message(view=self)


@dataclasses.dataclass(frozen=True)
class LookupInfo:
    player_id: str
    platform: Optional[rlapi.Platform] = None
    lookup_method: Optional[LookupMethod] = None
    tracked: bool = False

    def __post_init__(self) -> None:
        if self.platform is not None and self.lookup_method is not None:
            return
        if self.platform is not None:
            raise TypeError("lookup_method cannot be None when platform is specified")
        if self.lookup_method is not None:
            raise TypeError("platform cannot be None when lookup_method is specified")

    async def lookup(self, rlapi_client: rlapi.Client) -> List[rlapi.Player]:
        if self.platform is None:
            return await rlapi_client.find_player(self.player_id)

        assert (
            self.lookup_method is not None
        ), "inconsistent state - should have been checked in __post_init__"
        if self.lookup_method is LookupMethod.id:
            return [await rlapi_client.get_player_by_id(self.platform, self.player_id)]
        return [
            await rlapi_client.get_player_by_name(self.platform, self.player_id),
        ]


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
            tracker_interval=DEFAULT_TRACKER_INTERVAL,
            tracker_max_subscriptions=5,
        )
        self.config.register_user(
            lookup_method=None,
            player_id=None,
            platform=None,
            tracked=False,
        )
        # keyed by (platform.name, player_id, guild_id)
        # no player ID in config vs player ID with no guilds
        # are treated differently
        self.config.init_custom(TRACKED_PLAYERS, 3)
        self.config.register_custom(TRACKED_PLAYERS, subscribed_channels=[])
        # optimization strategy for lookup of subscriptions by guild/channel
        # keyed by (guild_id, channel_id, platform.name)
        self.config.init_custom(GUILD_SUBSCRIPTIONS, 3)
        self.config.register_custom(GUILD_SUBSCRIPTIONS, ids=[])

        self.breakdown_lock = asyncio.Lock()
        self.breakdown_updated_at = 0.0
        self.rlapi_client: rlapi.Client  # assigned in cog_load()
        self.bundled_data_path = bundled_data_path(self)
        self.cog_data_path = cog_data_path(self)
        self._prepare_templates()

        self.tracker_task: Optional[asyncio.Task] = None
        self.tracker_interval = DEFAULT_TRACKER_INTERVAL
        self.tracker_subscriptions_enabled = True
        self.tracker_history_path = self.cog_data_path / "history/v1"
        self.tracker_history_path.mkdir(parents=True, exist_ok=True)

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
        self.tracker_interval = await self.config.tracker_interval()
        self.tracker_subscriptions_enabled = (
            await self.config.tracker_max_subscriptions() != 0
        )

    async def cog_unload(self) -> None:
        await self.stop_tracker()
        self.rlapi_client.destroy()

    async def start_tracker(self) -> None:
        if self.tracker_task is None:
            self.tracker_task = asyncio.create_task(self.live_tracker())

    async def stop_tracker(self) -> None:
        if self.tracker_task is not None:
            self.tracker_task.cancel()
            try:
                await self.tracker_task
            except asyncio.CancelledError:
                pass

    async def live_tracker(self) -> None:
        while True:
            try:
                await self.update_tracked_players()
            except Exception as e:
                log.error(
                    "An error occurred while updating tracked players.", exc_info=e
                )
            await asyncio.sleep(self.tracker_interval)

    def _get_tracker_key(self, player: rlapi.Player) -> str:
        platform = player.platform.value
        if player.user_id is not None:
            player_id = player.user_id
            lookup_method = LookupMethod.id.value
        else:
            player_id = player.user_name
            lookup_method = LookupMethod.name.value
        hashed_id = hashlib.sha256(player_id.encode()).hexdigest()

        return f"{platform}_{lookup_method}_{hashed_id}"

    def _get_tracker_path(self, tracker_key: str, tracker_id: Union[str, int]) -> Path:
        return self.tracker_history_path / f"{tracker_key}_{tracker_id}.csv"

    def _get_last_lines(self, path: Path, *, n: int = 1) -> List[str]:
        """Return n last lines ordered from the most recent to the least recent."""
        lines: List[str] = []
        try:
            fp = path.open("rb")
        except FileNotFoundError:
            return lines

        with fp:
            try:
                fp.seek(-2, os.SEEK_END)
            except OSError:
                return lines

            start = fp.tell()
            while start >= 0 and len(lines) < n:
                fp.seek(start, os.SEEK_SET)

                while fp.read(1) != b"\n":
                    try:
                        fp.seek(-2, os.SEEK_CUR)
                    except OSError:
                        fp.seek(0)
                        lines.append(fp.readline().decode())
                        return lines

                start = fp.tell() - 2
                lines.append(fp.readline().decode())

        return lines

    def _get_playlist_history_reader(self, lines: Iterable[str]) -> csv.DictReader:
        return csv.DictReader(
            lines, fieldnames=PLAYLIST_HISTORY_V1_FIELDS, quoting=csv.QUOTE_NONNUMERIC
        )

    def _get_playlist_history_writer(self, fp: TextIO) -> csv.DictWriter:
        return csv.DictWriter(
            fp, fieldnames=PLAYLIST_HISTORY_V1_FIELDS, quoting=csv.QUOTE_NONNUMERIC
        )

    def _get_rewards_history_reader(self, lines: Iterable[str]) -> csv.DictReader:
        return csv.DictReader(
            lines, fieldnames=REWARDS_HISTORY_V1_FIELDS, quoting=csv.QUOTE_NONNUMERIC
        )

    def _get_rewards_history_writer(self, fp: TextIO) -> csv.DictWriter:
        return csv.DictWriter(
            fp, fieldnames=REWARDS_HISTORY_V1_FIELDS, quoting=csv.QUOTE_NONNUMERIC
        )

    async def update_tracked_players(self) -> None:
        tracked_players = await self.config.custom(TRACKED_PLAYERS).all()
        for raw_platform, data in tracked_players.items():
            if not data:
                continue

            platform = rlapi.Platform[raw_platform]
            async for player in self.rlapi_client.get_players(platform, ids=data):
                changes = await self.update_player_trackers(player)
                if self.tracker_subscriptions_enabled and changes:
                    await self.notify_subscribed_channels(
                        player, data[player.user_id], changes
                    )

    async def update_player_trackers(self, player: rlapi.Player) -> PlaylistChangeSet:
        updated_at = time.time()
        tracker_key = self._get_tracker_key(player)
        cancelled_exc: Union[None, asyncio.CancelledError] = None

        changes: PlaylistChangeSet = {}
        for playlist in player.playlists.values():
            change = self.update_playlist_tracker(tracker_key, updated_at, playlist)
            if change is not None and isinstance(playlist.key, rlapi.PlaylistKey):
                changes[playlist.key] = change

            try:
                await asyncio.sleep(0)
            except asyncio.CancelledError as exc:
                if cancelled_exc is None:
                    cancelled_exc = exc

        self.update_rewards_tracker(tracker_key, updated_at, player.season_rewards)
        if cancelled_exc is not None:
            raise cancelled_exc

        return changes

    def _add_diff_field(
        self,
        embed: discord.Embed,
        field_name: str,
        before: Dict[str, Any],
        after: Dict[str, Any],
        key: str,
        *,
        value_mapper: Callable[[int], str] = str,
        diff: Optional[int] = None,
        inline: bool = True,
        always_show: bool = False,
    ) -> None:
        before_val = int(before[key])
        after_val = int(after[key])
        if diff is None:
            diff = after_val - before_val
        if diff:
            before_repr = value_mapper(before_val)
            after_repr = value_mapper(after_val)
            embed.add_field(
                name=field_name,
                value=f"{before_repr} -> **{after_repr}** ({diff:+d})",
                inline=inline,
            )
        elif always_show:
            after_repr = value_mapper(after_val)
            embed.add_field(
                name=field_name,
                value=f"**{after_repr}**",
                inline=inline,
            )

    def _add_after_field(
        self,
        embed: discord.Embed,
        field_name: str,
        before: Dict[str, Any],
        after: Dict[str, Any],
        key: str,
        *,
        value_mapper: Callable[[int], str] = str,
        inline: bool = True,
        always_show: bool = False,
    ) -> None:
        before_val = int(before[key])
        after_val = int(after[key])
        if before[key] != after[key]:
            before_repr = value_mapper(before_val)
            after_repr = value_mapper(after_val)
            embed.add_field(
                name=field_name,
                value=f"**{after_repr}** (previously {before_repr})",
                inline=inline,
            )
        elif always_show:
            after_repr = value_mapper(after_val)
            embed.add_field(
                name=field_name,
                value=f"**{after_repr}**",
                inline=inline,
            )

    def _format_estimate(self, value: Optional[int]) -> str:
        if value is None:
            return "**N/A**"
        return f"**{value:+d}**"

    async def notify_subscribed_channels(
        self,
        player: rlapi.Player,
        subscribed_guilds: Dict[str, Dict[str, Any]],
        changes: PlaylistChangeSet,
    ) -> None:
        author_name = f"{player.user_name} on {player.platform} changed!"
        embeds = []
        for playlist_key, (before, after) in changes.items():
            embed = discord.Embed(title=str(playlist_key))
            embed.set_author(name=author_name)
            self._add_diff_field(
                embed,
                "Rank",
                before,
                after,
                "tier",
                value_mapper=rlapi.RANKS.__getitem__,
                always_show=True,
            )
            if not (
                before["tier"] == after["tier"]
                and after["tier"] in (0, len(rlapi.RANKS) - 1)
            ):
                diff = (
                    int(after["tier"]) * len(rlapi.DIVISIONS) + int(after["division"])
                ) - (
                    int(before["tier"]) * len(rlapi.DIVISIONS) + int(before["division"])
                )
                self._add_diff_field(
                    embed,
                    "Division",
                    before,
                    after,
                    "division",
                    value_mapper=rlapi.DIVISIONS.__getitem__,
                    diff=diff,
                    always_show=True,
                )
            self._add_diff_field(embed, "Skill Rating", before, after, "skill")
            self._add_after_field(
                embed,
                "Win Streak",
                before,
                after,
                "win_streak",
                value_mapper="{:+}".format,
                inline=False,
            )
            tier_estimates = player.playlists[playlist_key].tier_estimates
            if not (tier_estimates.div_down is None and tier_estimates.div_up is None):
                embed.add_field(
                    name="MMR estimate for division change",
                    value=(
                        f"{self._format_estimate(tier_estimates.div_down)}"
                        " / "
                        f"{self._format_estimate(tier_estimates.div_up)}"
                    ),
                    inline=False,
                )
            if not (
                tier_estimates.tier_down is None and tier_estimates.tier_up is None
            ):
                embed.add_field(
                    name="MMR estimate for rank change",
                    value=(
                        f"{self._format_estimate(tier_estimates.tier_down)}"
                        " / "
                        f"{self._format_estimate(tier_estimates.tier_up)}"
                    ),
                    inline=False,
                )
            self._add_after_field(
                embed, "Matches played", before, after, "matches_played"
            )
            self._add_after_field(
                embed,
                "Lifetime matches played",
                before,
                after,
                "lifetime_matches_played",
            )
            embeds.append(embed)

        for raw_guild_id, data in subscribed_guilds.items():
            guild_id = int(raw_guild_id)
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            if await self.bot.cog_disabled_in_guild(self, guild):
                return

            for channel_id in data["subscribed_channels"]:
                channel = channel = cast(
                    Optional[
                        Union[
                            discord.TextChannel,
                            discord.VoiceChannel,
                            discord.StageChannel,
                            discord.Thread,
                        ]
                    ],
                    guild.get_channel_or_thread(channel_id),
                )
                if channel is None:
                    continue

                try:
                    if not can_user_send_messages_in(guild.me, channel):
                        raise RuntimeError

                    await channel.send(embeds=embeds)
                except (discord.Forbidden, RuntimeError):
                    log.error(
                        "Bot can't send messages in channel with ID %s (guild ID: %s)",
                        channel_id,
                        guild.id,
                    )
                    continue

    def update_playlist_tracker(
        self, tracker_key: str, updated_at: float, playlist: rlapi.Playlist
    ) -> Optional[PlaylistChange]:
        if playlist.key == 0:
            # no matches played field on Unranked playlist
            return None

        tracker_path = self._get_tracker_path(tracker_key, int(playlist.key))
        last_lines = self._get_last_lines(tracker_path)
        if last_lines:
            last_change = next(self._get_playlist_history_reader(last_lines))
            last_lifetime_matches_played = last_change["lifetime_matches_played"]
            if last_lifetime_matches_played == playlist.lifetime_matches_played:
                return None

        row = {
            "updated_at": updated_at,
            "tier": playlist.tier,
            "division": playlist.division,
            "mu": playlist.mu,
            "skill": playlist.skill,
            "sigma": playlist.sigma,
            "win_streak": playlist.win_streak,
            "matches_played": playlist.matches_played,
            "lifetime_matches_played": playlist.lifetime_matches_played,
            "placement_matches_played": playlist.placement_matches_played,
        }

        with open(tracker_path, "a", encoding="utf-8") as fp:
            writer = self._get_playlist_history_writer(fp)
            writer.writerow(row)

        if not last_lines:
            return None
        return (last_change, row)

    def update_rewards_tracker(
        self, tracker_key: str, updated_at: float, rewards: rlapi.SeasonRewards
    ) -> None:
        tracker_path = self._get_tracker_path(tracker_key, "season_rewards")
        last_lines = self._get_last_lines(tracker_path)
        if last_lines:
            last_change = next(self._get_rewards_history_reader(last_lines))
            if (
                last_change["level"] == rewards.level
                and last_change["wins"] == rewards.wins
            ):
                return

        with open(tracker_path, "a", encoding="utf-8") as fp:
            writer = self._get_rewards_history_writer(fp)
            row = {
                "updated_at": updated_at,
                "level": rewards.level,
                "wins": rewards.wins,
            }
            writer.writerow(row)

    async def get_gains_for(
        self, player: rlapi.Player, playlists: Tuple[rlapi.PlaylistKey, ...]
    ) -> Dict[rlapi.PlaylistKey, int]:
        tracker_key = self._get_tracker_key(player)
        gains = {}
        for playlist_key in playlists:
            playlist = player.playlists[playlist_key]

            tracker_path = self._get_tracker_path(tracker_key, int(playlist_key))
            last_lines = self._get_last_lines(tracker_path, n=2)
            if not last_lines:
                await asyncio.sleep(0)
                continue
            last_changes = list(self._get_playlist_history_reader(last_lines))

            last_lifetime_matches_played = int(
                last_changes[0]["lifetime_matches_played"]
            )
            if (last_lifetime_matches_played + 1) == playlist.lifetime_matches_played:
                gains[playlist_key] = playlist.skill - int(last_changes[0]["skill"])
            elif (
                last_lifetime_matches_played == playlist.lifetime_matches_played
                and len(last_changes) >= 2
            ):
                gains[playlist_key] = playlist.skill - int(last_changes[1]["skill"])
            await asyncio.sleep(0)

        return gains

    async def red_get_data_for_user(self, *, user_id: int) -> Dict[str, BytesIO]:
        try:
            lookup_info = await self._get_player_data_by_user_id(user_id)
        except errors.PlayerDataNotFound:
            return {}
        contents = (
            f"Rocket League game account for Discord user with ID {user_id}:\n"
            f"- Platform: {lookup_info.platform}\n"
            f"- Lookup method: {lookup_info.lookup_method}\n"
            f"- Player ID: {lookup_info.player_id}\n"
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

    async def _get_player_data_by_user_id(self, user_id: int) -> LookupInfo:
        user_data = await self.config.user_from_id(user_id).all()
        player_id, raw_platform = user_data["player_id"], user_data["platform"]
        if player_id is None:
            raise errors.PlayerDataNotFound(
                f"Couldn't find player data for discord user with ID {user_id}"
            )

        platform = rlapi.Platform[raw_platform]
        try:
            lookup_method = LookupMethod(user_data["lookup_method"])
        except ValueError:
            if platform in (rlapi.Platform.steam, rlapi.Platform.epic):
                lookup_method = LookupMethod.id
            else:
                lookup_method = LookupMethod.name

        tracked = user_data["tracked"]

        return LookupInfo(player_id, platform, lookup_method, tracked=tracked)

    async def _get_player_data_by_user(self, user: discord.abc.User) -> LookupInfo:
        return await self._get_player_data_by_user_id(user.id)

    async def _get_players(
        self, player_ids: List[LookupInfo]
    ) -> Tuple[rlapi.Player, ...]:
        players: List[rlapi.Player] = []
        for lookup_info in player_ids:
            with contextlib.suppress(rlapi.PlayerNotFound):
                players += await lookup_info.lookup(self.rlapi_client)
        if not players:
            raise rlapi.PlayerNotFound
        # using dict.fromkeys() to make duplicates go away
        return tuple(dict.fromkeys(players))

    async def _maybe_get_players(
        self,
        ctx: commands.Context,
        player_ids: List[LookupInfo],
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
    ) -> int:
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
            return result
        return 0

    def _generate_image(
        self,
        template: RLStatsImageTemplate,
        playlists: Tuple[rlapi.PlaylistKey, ...],
        gains: Dict[rlapi.PlaylistKey, int],
        player: rlapi.Player,
    ) -> BytesIO:
        result = template.generate_image(player, playlists, gains)
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

            lookups: List[LookupInfo] = []
            discord_user = None
            if player_id is None:
                try:
                    lookups.append(await self._get_player_data_by_user(ctx.author))
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
                        lookups.append(
                            await self._get_player_data_by_user(discord_user)
                        )
                    except errors.PlayerDataNotFound:
                        discord_user = None
                lookups.append(LookupInfo(player_id))

            players = await self._maybe_get_players(ctx, lookups)
            if players is None:
                return

            try:
                player_idx = await self._choose_player(ctx, players)
            except errors.NoChoiceError as e:
                log.debug(e)
                await ctx.send(
                    "You didn't select a profile that you would like to check."
                )
                return
            player = players[player_idx]

            # TODO: This should probably be handled in rlapi module
            # be careful when touching this part,
            # we rely on `player.get_playlist` not returning None in .image
            for playlist_key in playlists:
                if playlist_key not in player.playlists:
                    player.add_playlist({"playlist": playlist_key.value})

            gains = await self.get_gains_for(player, playlists)

            # be extra careful when changing this (mypy won't type check this)
            fp = await self._run_in_executor(
                self._generate_image, template, playlists, gains, player
            )
        if discord_user is not None and player_idx == 0:
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
            file=discord.File(
                fp,
                f"{player.platform.value}"
                "_"
                f"{player.user_id or player.user_name}"
                "_profile.png",
            ),
        )

    @commands.command()
    async def rlconnect(self, ctx: commands.Context, *, player_id: str) -> None:
        """Connect game profile with your Discord account."""
        async with ctx.typing():
            if not await self._check_client_credentials(ctx):
                return

            lookup_info = None
            try:
                lookup_info = await self._get_player_data_by_user(ctx.author)
            except errors.PlayerDataNotFound:
                pass
            if (
                lookup_info is not None
                and lookup_info.tracked
                and lookup_info.platform is not None
            ):
                await self._maybe_untrack_player(
                    lookup_info.platform, lookup_info.player_id
                )

            players = await self._maybe_get_players(ctx, [LookupInfo(player_id)])
            if players is None:
                # message already sent by `_maybe_get_players()` when it returns `None`
                return

            try:
                player_idx = await self._choose_player(ctx, players)
            except errors.NoChoiceError as e:
                log.debug(str(e))
                await ctx.send(
                    "You didn't select a profile that you would like to connect."
                )
                return
            player = players[player_idx]

            scope = self.config.user(ctx.author)
            await scope.platform.set(player.platform.name)
            if player.user_id is not None:
                await scope.lookup_method.set(LookupMethod.id.value)
                await scope.player_id.set(str(player.user_id))
                if lookup_info is not None and lookup_info.tracked:
                    await self._track_player(player.platform, str(player.user_id))
            else:
                await scope.lookup_method.set(LookupMethod.name.value)
                await scope.player_id.set(player.user_name)
                await scope.tracked.set(False)

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
        lookup_info = await self._get_player_data_by_user(ctx.author)
        if lookup_info.tracked and lookup_info.platform is not None:
            await self._maybe_untrack_player(
                lookup_info.platform, lookup_info.player_id
            )
        await self.config.user(ctx.author).clear()
        await ctx.send("Your game account was successfully disconnected from Discord!")

    @commands.command()
    async def rltrackme(self, ctx: commands.Context) -> None:
        """
        Enable live tracking of the game profile associated with your Discord account
        through `[p]rlconnect`.

        Tracking is only supported when connected with the following platforms:
        - Steam
        - Epic
        - PlayStation - only when connected with a [PSN Account ID]\
        (https://psn.flipscreen.games) or its connected Epic account
        - Xbox One - only when connected with an [Xbox services ID (XUID)]\
        (https://www.cxkes.me/xbox/xuid) or its connected Epic account
        """
        try:
            lookup_info = await self._get_player_data_by_user(ctx.author)
        except errors.PlayerDataNotFound:
            await ctx.send(
                "Your game account is not connected with Discord."
                " If you want to live track your stats,"
                " connect your account using command:"
                f" {inline(f'{ctx.clean_prefix}rlconnect <player_id>')}"
            )
            return

        players = await self._maybe_get_players(ctx, [lookup_info])
        if not players:
            await ctx.send(
                "Could not find the account that you have connected with your Discord."
                " Try reconnecting it using command:"
                f" {inline(f'{ctx.clean_prefix}rlconnect <player_id>')}"
            )
            return

        player = players[0]
        if not await self._is_lookup_by_id_or_send_error(ctx, player):
            return
        user_id = player.user_id or ""

        # ensure that we actually have the ID in user's config
        user_scope = self.config.user(ctx.author)
        await user_scope.lookup_method.set(LookupMethod.id.value)
        await user_scope.player_id.set(user_id)

        # set tracked flag to auto-enroll on `[p]rlconnect`
        await user_scope.tracked.set(True)
        await self._track_player(player.platform, user_id)

        await ctx.send("Your game account is now tracked for changes automatically.")

    @commands.admin_or_can_manage_channel()
    @commands.group(name="rltracker")
    async def rltracker(self, ctx: commands.GuildContext) -> None:
        """RLStats live tracker server settings."""

    @commands.admin_or_can_manage_channel()
    @rltracker.command(name="subscribe")
    async def subscribe(self, ctx: commands.GuildContext, *, player_id: str) -> None:
        """Subscribe current channel to updates of the given game profile."""
        lookups = []
        try:
            discord_user = await commands.MemberConverter().convert(ctx, player_id)
        except commands.BadArgument:
            pass
        else:
            try:
                lookups.append(await self._get_player_data_by_user(discord_user))
            except errors.PlayerDataNotFound:
                pass
        lookups.append(LookupInfo(player_id))

        players = await self._maybe_get_players(ctx, lookups)
        if players is None:
            return

        try:
            player_idx = await self._choose_player(ctx, players)
        except errors.NoChoiceError as e:
            log.debug(e)
            await ctx.send(
                "You didn't select a profile that you would like to subscribe to."
            )
            return
        player = players[player_idx]

        if not await self._is_lookup_by_id_or_send_error(ctx, player):
            return

        max_subscriptions = await self.config.tracker_max_subscriptions()
        async with self.config.custom(
            GUILD_SUBSCRIPTIONS,
            str(ctx.guild.id),
            str(ctx.channel.id),
        ).all() as channel_data:
            # validate subscription count
            subscription_count = sum(
                1
                for platform_data in channel_data.values()
                for _ in platform_data["ids"]
            )
            if subscription_count >= max_subscriptions:
                await ctx.send(
                    "This channel is already at max number of subscriptions set"
                    " by the bot owner."
                )
                return

            player_id = str(player.user_id)
            # add to guild subscriptions group
            platform_data = channel_data.setdefault(player.platform.name, {"ids": []})
            ids = platform_data["ids"]
            if player_id not in ids:
                ids.append(player_id)

            # add to tracked players group
            scope = self.config.custom(
                TRACKED_PLAYERS,
                player.platform.name,
                player_id,
                str(ctx.guild.id),
            )
            async with scope.subscribed_channels() as subscribed_channels:
                if ctx.channel.id not in subscribed_channels:
                    subscribed_channels.append(ctx.channel.id)

        await ctx.send(
            "Subscribed the current channel to live tracker updates for"
            f" {player.user_name} (Platform: {player.platform}; ID: {player.user_id})"
        )

    @commands.admin_or_can_manage_channel()
    @rltracker.command(name="unsubscribe")
    async def unsubscribe(self, ctx: commands.GuildContext) -> None:
        """List and delete profile update subscriptions in the server."""
        guild_data = await self.config.custom(
            GUILD_SUBSCRIPTIONS, str(ctx.guild.id)
        ).all()
        if not guild_data:
            await ctx.send(
                "There are no active profile update subscriptions in this server."
            )
            return

        view = GuildSubscriptionView(ctx, self, guild_data)
        await view.send()

    async def _is_lookup_by_id_or_send_error(
        self, ctx: commands.Context, player: rlapi.Player
    ) -> bool:
        if player.user_id is not None:
            return True
        if player.platform == rlapi.Platform.switch:
            await ctx.send(
                "Tracking for Nintendo users is only supported"
                " when connected through an Epic account."
            )
        elif player.platform == rlapi.Platform.ps4:
            await ctx.send(
                "Tracking for PlayStation users is only supported when connected with"
                " a [PSN Account ID](https://psn.flipscreen.games)"
                " or its connected Epic account."
            )
        elif player.platform == rlapi.Platform.xboxone:
            await ctx.send(
                "Tracking for Xbox One users is only supported when connected with"
                " an [Xbox services ID (XUID)](https://www.cxkes.me/xbox/xuid)"
                " or its connected Epic account."
            )
        else:
            await ctx.send(
                "Unexpected error: could not find User ID for your game account."
                " Please report this to the bot's owner along with the platform and ID"
                " of the game profile that you have connected to this Discord account."
            )
        return False

    async def _track_player(self, platform: rlapi.Platform, player_id: str) -> None:
        platform_scope = self.config.custom(TRACKED_PLAYERS, platform.name)
        player_scope = self.config.custom(TRACKED_PLAYERS, platform.name, player_id)
        async with player_scope.get_lock():
            try:
                await platform_scope.get_raw(player_id)
            except KeyError:
                await player_scope.set({})

    async def _maybe_untrack_player(
        self, platform: rlapi.Platform, player_id: str
    ) -> None:
        player_scope = self.config.custom(TRACKED_PLAYERS, platform.name, player_id)
        async with player_scope.get_lock():
            data = await player_scope.all()
            if not data:
                await player_scope.clear()

    async def _untrack_player(self, platform: rlapi.Platform, player_id: str) -> None:
        player_scope = self.config.custom(TRACKED_PLAYERS, platform.name, player_id)
        await player_scope.clear()

    @commands.Cog.listener()
    async def on_red_api_tokens_update(
        self, service_name: str, api_tokens: Mapping[str, str]
    ) -> None:
        if service_name != "rocket_league":
            return

        client_credentials = await self._get_client_credentials(api_tokens)
        self.rlapi_client.update_client_credentials(**client_credentials)
