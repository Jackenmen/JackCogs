from io import BytesIO
from math import ceil
import asyncio

import aiohttp
import discord
from redbot.core import commands
from redbot.core.data_manager import bundled_data_path
from PIL import ImageFont

from . import errors
from .figures import Point
from .image import CoordsInfo, Mee6RankImageTemplate


class Mee6Rank(commands.Cog):
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

    def __init__(self, bot):
        self._session = aiohttp.ClientSession(loop=bot.loop)
        self.bot = bot
        self.loop = bot.loop
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
            avatar_mask=self.bundled_data_path / "avatar_mask.png",
        )

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.member)
    async def mee6rank(self, ctx, member: discord.Member = None):
        async with ctx.typing():
            if member is None:
                member = ctx.author
            player = await self._get_player(member)
            if player is None:
                return_form = "your" if member is ctx.author else "member's"
                return await ctx.send(f"Could not find {return_form} Mee6 rank.")

            role_rewards = player["role_rewards"]
            embed = discord.Embed(title=f"{member.name} Mee6 rank")
            embed.add_field(name="Level", value=player["level"])
            embed.add_field(name="XP amount", value=player["xp"])
            xp_needed = self._xp_to_desired(player["level"] + 1) - player["xp"]
            embed.add_field(name="XP needed to next level", value=xp_needed)
            embed.add_field(
                name="Average amount of messages to next lvl",
                value=self._message_amount_from_xp(xp_needed)[1],
            )
            next_role_reward = self._next_role_reward(role_rewards, player["level"])
            if next_role_reward is not None:
                xp_needed = self._xp_to_desired(next_role_reward["rank"]) - player["xp"]
                embed.add_field(
                    name=f"XP to next role - {next_role_reward['role']['name']}",
                    value=xp_needed,
                )
                embed.add_field(
                    name=(
                        "Average amount of messages to next role"
                        f" - {next_role_reward['role']['name']}"
                    ),
                    value=self._message_amount_from_xp(xp_needed)[1],
                )
            await ctx.send(embed=embed)

    @commands.is_owner()
    @commands.command()
    @commands.guild_only()
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.member)
    async def mee6rankimage(self, ctx, member: discord.Member = None):
        if member is None:
            member = ctx.author
        player = await self._get_player(member, get_avatar=True)
        if player is None:
            return_form = "your" if member is ctx.author else "member's"
            return await ctx.send(f"Could not find {return_form} Mee6 rank.")

        image = self.template.generate_image(player)
        bytes_object = BytesIO()
        image.save(bytes_object, format="PNG", quality=100)
        bytes_object.seek(0)
        await ctx.send(file=discord.File(bytes_object, filename="card.png"))

    async def _request(self, guild_id, page):
        url = (
            "https://mee6.xyz/api/plugins/levels/leaderboard/"
            f"{guild_id}?page={page}&limit=999"
        )
        for tries in range(5):
            async with self._session.get(url) as resp:
                if 300 > resp.status >= 200:
                    return await resp.json()

                # received 500 or 502 error, API has some troubles, retrying
                if resp.status in {500, 502}:
                    await asyncio.sleep(1 + tries * 2, loop=self.loop)
                    continue
                raise errors.HTTPException()
        # still failed after 5 tries
        raise errors.HTTPException()

    async def _get_player(self, member: discord.Member, *, get_avatar=False):
        player = None
        page = 0
        guild_id = member.guild.id
        while player is None:
            leaderboard = await self._request(guild_id, page)
            players = leaderboard["players"]
            if not players:
                return None
            for idx, p in enumerate(players, 1):
                if p["id"] == str(member.id):
                    player = p
                    player["rank"] = page * 999 + idx
                    break
            page += 1
        player["member_obj"] = member
        player["role_rewards"] = leaderboard["role_rewards"]
        if get_avatar:
            avatar = BytesIO()
            avatar.name = f"{member.id}.png"
            await member.avatar_url_as(format="png").save(avatar)
            player["avatar"] = avatar
        return player

    def _xp_to_desired(self, desired_level):
        return ceil(
            5
            / 6
            * desired_level
            * (2 * desired_level * desired_level + 27 * desired_level + 91)
        )

    def _message_amount_from_xp(self, xp_needed):
        minimum = ceil(xp_needed / self.MAX_XP_GAIN)
        avg = ceil(xp_needed / (self.AVG_XP_GAIN / 2))
        maximum = ceil(xp_needed / self.MIN_XP_GAIN)
        return (minimum, avg, maximum)

    def _next_role_reward(self, role_rewards, current_level):
        next_role_reward = None
        for role_reward in role_rewards:
            if role_reward["rank"] > current_level:
                try:
                    next_role_reward = min(
                        role_reward, next_role_reward, key=lambda x: x["rank"]
                    )
                except TypeError:
                    next_role_reward = role_reward
        return next_role_reward
