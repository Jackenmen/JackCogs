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
import functools
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Any, Callable, Dict, Literal, TypeVar, Union, overload

import aiohttp
import discord
from PIL import ImageFont
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands import NoParseOptional as Optional
from redbot.core.data_manager import bundled_data_path

from . import errors
from .figures import Point
from .image import CoordsInfo, Mee6RankImageTemplate
from .player import Player, PlayerWithAvatar
from .utils import json_or_text

log = logging.getLogger("red.jackcogs.mee6rank")

T = TypeVar("T")
RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]


class Mee6Rank(commands.Cog):
    """Get detailed information about your Mee6 rank."""

    MIN_XP_GAIN = 15
    MAX_XP_GAIN = 25
    AVG_XP_GAIN = (MIN_XP_GAIN + MAX_XP_GAIN) / 2
    COORDS = {
        "level_number": CoordsInfo(Point(882, 100), "Poppins60"),
        "level_caption": CoordsInfo(Point(882, 100), "Poppins24"),
        "rank_number": CoordsInfo(Point(882, 100), "Poppins60"),
        "rank_caption": CoordsInfo(Point(882, 100), "Poppins24"),
        "username": CoordsInfo(Point(274, 174), "DejaVu40"),
        "discriminator": CoordsInfo(Point(274, 166), "DejaVu24"),
        "progressbar": CoordsInfo(Point(256, 182), None),
        "needed_xp": CoordsInfo(Point(882, 170), "Poppins24"),
        "current_xp": CoordsInfo(Point(882, 166), "Poppins24"),
        "avatar": CoordsInfo(Point(40, 60), None),
    }

    def __init__(self, bot: Red) -> None:
        super().__init__()
        self._session = aiohttp.ClientSession()
        self.bot = bot
        self.loop: asyncio.AbstractEventLoop = bot.loop
        self._executor = ThreadPoolExecutor()
        self.bundled_data_path = bundled_data_path(self)
        self.fonts = {
            "Poppins24": ImageFont.truetype(
                str(self.bundled_data_path / "fonts/Poppins-Regular.ttf"), 24
            ),
            "Poppins60": ImageFont.truetype(
                str(self.bundled_data_path / "fonts/Poppins-Regular.ttf"), 60
            ),
            "DejaVu24": ImageFont.truetype(
                str(self.bundled_data_path / "fonts/DejaVuSans.ttf"), 24
            ),
            "DejaVu40": ImageFont.truetype(
                str(self.bundled_data_path / "fonts/DejaVuSans.ttf"), 40
            ),
        }
        self.template = Mee6RankImageTemplate(
            coords=self.COORDS,
            fonts=self.fonts,
            card_base=self.bundled_data_path / "card_base.png",
            progressbar=self.bundled_data_path / "progressbar.png",
            progressbar_rounding_mask=(
                self.bundled_data_path / "progressbar_rounding_mask.png"
            ),
            avatar_mask=self.bundled_data_path / "avatar_mask.png",
        )

    async def cog_unload(self) -> None:
        await self._session.close()

    async def red_get_data_for_user(self, *, user_id: int) -> Dict[str, Any]:
        # this cog does not story any data
        return {}

    async def red_delete_data_for_user(
        self, *, requester: RequestType, user_id: int
    ) -> None:
        # this cog does not story any data
        pass

    async def _run_in_executor(
        self, func: Callable[..., T], *args: Any, **kwargs: Any
    ) -> T:
        return await self.loop.run_in_executor(
            self._executor, functools.partial(func, *args, **kwargs)
        )

    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.member)
    @commands.command()
    async def mee6rank(
        self, ctx: commands.GuildContext, member: Optional[discord.Member] = None
    ) -> None:
        """Get detailed information about Mee6 rank for you or given member."""
        async with ctx.typing():
            if (player := await self._maybe_get_player(ctx, member)) is None:
                return

            embed = discord.Embed(
                title=f"Mee6 rank for {player.member.name}", color=0x62D3F5
            )
            embed.add_field(name="Level", value=str(player.level))
            embed.add_field(name="XP amount", value=str(player.total_xp))
            xp_needed = player.xp_until_next_level
            embed.add_field(name="XP needed to next level", value=str(xp_needed))
            embed.add_field(
                name="Average amount of messages to next lvl",
                value=str(self._message_amount_from_xp(xp_needed)),
            )
            next_role_reward = player.next_role_reward
            if next_role_reward is not None:
                xp_needed = player.xp_until_level(next_role_reward.rank)
                embed.add_field(
                    name=f"XP to next role - {next_role_reward.role.name}",
                    value=str(xp_needed),
                )
                embed.add_field(
                    name=(
                        "Average amount of messages to next role"
                        f" - {next_role_reward.role.name}"
                    ),
                    value=str(self._message_amount_from_xp(xp_needed)),
                )
            await ctx.send(embed=embed)

    def _generate_image(self, player: PlayerWithAvatar) -> BytesIO:
        image = self.template.generate_image(player)
        fp = BytesIO()
        image.save(fp, format="PNG", quality=100)
        fp.seek(0)
        return fp

    @commands.guild_only()
    @commands.bot_has_permissions(attach_files=True)
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.member)
    @commands.command()
    async def mee6rankimage(
        self, ctx: commands.GuildContext, member: Optional[discord.Member] = None
    ) -> None:
        """
        Get Mee6 rank image for you or given member.

        This tries to imitate Mee6's !rank command.
        """
        if (
            player := await self._maybe_get_player(ctx, member, get_avatar=True)
        ) is None:
            return

        fp = await self._run_in_executor(self._generate_image, player)

        await ctx.send(file=discord.File(fp, filename="card.png"))

    async def _request(self, guild_id: int, page: int) -> Dict[str, Any]:
        url = (
            "https://mee6.xyz/api/plugins/levels/leaderboard/"
            f"{guild_id}?page={page}&limit=999"
        )
        for tries in range(5):
            async with self._session.get(url) as resp:
                data = await json_or_text(resp)
                if 300 > resp.status >= 200:
                    assert isinstance(data, dict), "mypy"
                    return data

                if resp.status == 404:
                    raise errors.GuildNotFound(resp, data)

                # received 500 or 502 error, API has some troubles, retrying
                if resp.status in {500, 502}:
                    # maybe switch this to exponential backoff someday...
                    await asyncio.sleep(1 + tries * 2)
                    continue
                raise errors.HTTPException(resp, data)
        # still failed after 5 tries
        raise errors.HTTPException(resp, data)

    @overload
    async def _maybe_get_player(
        self,
        ctx: commands.GuildContext,
        member: Optional[discord.Member],
        *,
        get_avatar: Literal[True] = ...,
    ) -> Optional[PlayerWithAvatar]:
        ...

    @overload
    async def _maybe_get_player(
        self,
        ctx: commands.GuildContext,
        member: Optional[discord.Member],
        *,
        get_avatar: Literal[False] = ...,
    ) -> Optional[Player]:
        ...

    async def _maybe_get_player(
        self,
        ctx: commands.GuildContext,
        member: Optional[discord.Member],
        *,
        get_avatar: Union[Literal[True], Literal[False]] = False,  # why mypy :(
    ) -> Optional[Player]:
        try:
            player = await self._get_player(member or ctx.author, get_avatar=get_avatar)
        except errors.GuildNotFound:
            await ctx.send("There's no Mee6 leaderboard for this guild.")
        except errors.HTTPException as e:
            log.error(str(e))
            if e.status >= 500:
                await ctx.send(
                    "Mee6 API experiences some issues right now. Try again later."
                )
            else:
                await ctx.send(
                    "Mee6 API can't process this request."
                    " If this keeps happening, inform bot's owner about this error."
                )
        else:
            if player is not None:
                return player

            if member is None:
                await ctx.send("I wasn't able to find your Mee6 rank.")
            else:
                await ctx.send("I wasn't able to find Mee6 rank for the given member.")

        return None

    @overload
    async def _get_player(
        self, member: discord.Member, *, get_avatar: Literal[True] = ...
    ) -> Optional[PlayerWithAvatar]:
        ...

    @overload
    async def _get_player(
        self, member: discord.Member, *, get_avatar: Literal[False] = ...
    ) -> Optional[Player]:
        ...

    async def _get_player(
        self, member: discord.Member, *, get_avatar: bool = False
    ) -> Optional[Player]:
        """
        Gets Mee6 player object from `discord.Member`.
        Returns `None` when player wasn't found.

        Raises
        ------
        HTTPException
            Raised when the API returned error response.
        """
        player_data: Optional[Dict[str, Any]] = None
        page = 0
        guild_id = member.guild.id
        while player_data is None:
            leaderboard = await self._request(guild_id, page)
            players = leaderboard["players"]
            if not players:
                return None

            for idx, p in enumerate(players, 1):
                if p["id"] == str(member.id):
                    player_data = p
                    player_data["rank"] = page * 999 + idx
                    break
            page += 1

        if get_avatar:
            avatar = BytesIO(await member.display_avatar.with_format("png").read())
            avatar.name = f"{member.id}.png"
            return PlayerWithAvatar(
                player_data, member, leaderboard["role_rewards"], avatar
            )

        return Player(player_data, member, leaderboard["role_rewards"])

    def _message_amount_from_xp(self, xp_needed: int) -> int:
        return math.ceil(xp_needed / self.AVG_XP_GAIN)
