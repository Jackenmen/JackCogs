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

import logging
from itertools import zip_longest
from typing import Any, Awaitable, Callable, Dict, Literal, Optional

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands import GuildContext
from redbot.core.config import Config
from redbot.core.utils import AsyncIter, menus
from redbot.core.utils.chat_formatting import pagify

from .converters import MemberOrRole, MemberOrRoleOrVocalChannel

log = logging.getLogger("red.jackcogs.voicetools")

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]


class VoiceTools(commands.Cog):
    """Various tools to make voice channels better!"""

    def __init__(self, bot: Red) -> None:
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=6672039729, force_registration=True
        )
        default_guild = {
            "forcelimit_enabled": False,
            "forcelimit_ignore_member_list": [],
            "forcelimit_ignore_role_list": [],
            "forcelimit_ignore_vc_list": [],
            "vip_enabled": False,
            "vip_member_list": [],
            "vip_role_list": [],
        }
        self.config.register_guild(**default_guild)

    async def red_get_data_for_user(self, *, user_id: int) -> Dict[str, Any]:
        # this cog only stores user IDs which is not EUD
        return {}

    async def red_delete_data_for_user(
        self, *, requester: RequestType, user_id: int
    ) -> None:
        # this cog only stores user IDs which is not EUD
        if requester != "discord_deleted_user":
            return

        # but if Discord asks, you don't say no to them
        data = await self.config.all_guilds()
        async for guild_id, guild_data in AsyncIter(data.items(), steps=100):
            async with self.config.guild_from_id(guild_id).all() as guild_data:
                for group_name in ("forcelimit_ignore_member_list", "vip_member_list"):
                    guild_data[group_name] = [
                        member_id
                        for member_id in guild_data[group_name]
                        if member_id != user_id
                    ]

    @commands.guild_only()
    @commands.admin()
    @commands.group()
    async def voicetools(self, ctx: GuildContext) -> None:
        """Settings for voice tools."""

    @voicetools.group()
    async def forcelimit(self, ctx: GuildContext) -> None:
        """
        Settings for ForceLimit module.

        Force user limit to all members of the server including admins
        (Kicking is done the same way as in `[p]voicekick`)

        When combined with VIP module, this won't kick VIPs going over limit
        You can also add user or role to this module's ignore list,
        if you want to ignore going over limit while not raising user limit for channel
        or you can ignore chosen channels to stop bot from kicking users from it.
        """

    @forcelimit.command(name="enable")
    async def forcelimit_enable(self, ctx: GuildContext) -> None:
        """Enables ForceLimit module."""
        if not await self.config.guild(ctx.guild).forcelimit_enabled():
            await self.config.guild(ctx.guild).forcelimit_enabled.set(True)
            await ctx.send("ForceLimit module is now enabled on this server")
        else:
            await ctx.send("ForceLimit module is already enabled on this server")

    @forcelimit.command(name="disable")
    async def forcelimit_disable(self, ctx: GuildContext) -> None:
        """Disables ForceLimit module."""
        if await self.config.guild(ctx.guild).forcelimit_enabled():
            await self.config.guild(ctx.guild).forcelimit_enabled.set(False)
            await ctx.send("ForceLimit module is now disabled on this server")
        else:
            await ctx.send("ForceLimit module is already disabled on this server")

    @commands.bot_has_permissions(embed_links=True)
    @forcelimit.command(name="ignorelist")
    async def forcelimit_ignorelist(self, ctx: GuildContext) -> None:
        """
        Shows ignorelist of ForceLimit module.

        This can include members and roles which bypass forcelimit
        and voice channels which won't be checked.
        """
        guild_conf = self.config.guild(ctx.guild)
        # TODO: lower code repetition
        # TODO: remove member, role, voice channel IDs when they no longer exist
        ignore_member_list = await guild_conf.forcelimit_ignore_member_list()
        ignore_role_list = await guild_conf.forcelimit_ignore_role_list()
        ignore_vc_list = await guild_conf.forcelimit_ignore_vc_list()
        content_members = ", ".join(
            m.mention
            for m in map(ctx.guild.get_member, ignore_member_list)
            if m is not None
        )
        content_roles = ", ".join(
            r.mention
            for r in map(ctx.guild.get_role, ignore_role_list)
            if r is not None
        )
        content_vcs = ", ".join(
            vc.mention
            for vc in map(ctx.guild.get_channel, ignore_vc_list)
            if vc is not None
        )
        pages_members = list(pagify(content_members, page_length=1024))
        pages_roles = list(pagify(content_roles, page_length=1024))
        pages_vcs = list(pagify(content_vcs, page_length=1024))
        if not (pages_members or pages_roles or pages_vcs):
            await ctx.send("Ignore list is empty")
            return
        embed_pages = []
        pages = list(
            zip_longest(pages_members, pages_roles, pages_vcs, fillvalue="None")
        )
        len_pages = len(pages)
        for idx, page in enumerate(pages, start=1):
            embed = discord.Embed(title="Ignore List", colour=await ctx.embed_colour())
            embed.add_field(name="Members", value=page[0])
            embed.add_field(name="Roles", value=page[1])
            embed.add_field(name="Voice channels", value=page[2])
            embed.set_footer(text="Page {num}/{total}".format(num=idx, total=len_pages))
            embed_pages.append(embed)
        await menus.menu(ctx, embed_pages)

    @forcelimit.command(name="ignore")
    async def forcelimit_ignore(
        self, ctx: GuildContext, *ignores: MemberOrRoleOrVocalChannel
    ) -> None:
        """
        Adds members, roles or voice channels to ignorelist of ForceLimit module.

        Members and roles on ignorelist will bypass forcelimit
        (meaning - not getting kicked)

        Voice channels on ignorelist won't be checked
        (as if ForceLimit module was disabled for them)
        """
        guild_conf = self.config.guild(ctx.guild)
        ignore_member_list = await guild_conf.forcelimit_ignore_member_list()
        ignore_role_list = await guild_conf.forcelimit_ignore_role_list()
        ignore_vc_list = await guild_conf.forcelimit_ignore_vc_list()
        for ignore in ignores:
            if isinstance(ignore, discord.Role):
                ignore_list = ignore_role_list
            elif isinstance(ignore, discord.Member):
                ignore_list = ignore_member_list
            else:
                ignore_list = ignore_vc_list
            if ignore.id not in ignore_list:
                ignore_list.append(ignore.id)
            else:
                await ctx.send(f"{ignore} is already on ignore list")
        await guild_conf.forcelimit_ignore_member_list.set(ignore_member_list)
        await guild_conf.forcelimit_ignore_role_list.set(ignore_role_list)
        await guild_conf.forcelimit_ignore_vc_list.set(ignore_vc_list)
        await ctx.send("Ignore list updated")

    @forcelimit.command(name="unignore")
    async def forcelimit_unignore(
        self, ctx: GuildContext, *ignores: MemberOrRoleOrVocalChannel
    ) -> None:
        """
        Adds members, roles or voice channels to ignorelist of ForceLimit module

        Members and roles on ignorelist will bypass forcelimit
        (meaning - not getting kicked)

        Voice channels on ignorelist won't be checked
        (as if ForceLimit module was disabled for them)
        """
        guild_conf = self.config.guild(ctx.guild)
        ignore_member_list = await guild_conf.forcelimit_ignore_member_list()
        ignore_role_list = await guild_conf.forcelimit_ignore_role_list()
        ignore_vc_list = await guild_conf.forcelimit_ignore_vc_list()
        for ignore in ignores:
            if isinstance(ignore, discord.Role):
                ignore_list = ignore_role_list
            elif isinstance(ignore, discord.Member):
                ignore_list = ignore_member_list
            else:
                ignore_list = ignore_vc_list
            try:
                ignore_list.remove(ignore.id)
            except ValueError:
                await ctx.send(f"{ignore} is not on ignore list")
        await guild_conf.forcelimit_ignore_member_list.set(ignore_member_list)
        await guild_conf.forcelimit_ignore_role_list.set(ignore_role_list)
        await guild_conf.forcelimit_ignore_vc_list.set(ignore_vc_list)
        await ctx.send("Ignore list updated")

    @voicetools.group()
    async def vip(self, ctx: GuildContext) -> None:
        """
        Settings for VIP module.

        Set members and roles to not count to user limit in voice channel
        (limit will be raised accordingly after they join to make it possible)
        """

    @vip.command(name="enable")
    async def vip_enable(self, ctx: GuildContext) -> None:
        """Enables VIP module."""
        if not await self.config.guild(ctx.guild).vip_enabled():
            await self.config.guild(ctx.guild).vip_enabled.set(True)
            await ctx.send("VIP module is now enabled on this server")
        else:
            await ctx.send("VIP module is already enabled on this server")

    @vip.command(name="disable")
    async def vip_disable(self, ctx: GuildContext) -> None:
        """Disables VIP module."""
        if await self.config.guild(ctx.guild).vip_enabled():
            await self.config.guild(ctx.guild).vip_enabled.set(False)
            await ctx.send("VIP module is now disabled on this server")
        else:
            await ctx.send("VIP module is already disabled on this server")

    @commands.bot_has_permissions(embed_links=True)
    @vip.command(name="list")
    async def vip_list(self, ctx: GuildContext) -> None:
        """
        Shows vip list of VIP module.

        Members and roles specified here will not count to user limit in voice channel.
        """
        vip_member_list = await self.config.guild(ctx.guild).vip_member_list()
        vip_role_list = await self.config.guild(ctx.guild).vip_role_list()
        # TODO: lower code repetition
        # TODO: remove member, role, voice channel IDs when they no longer exist
        content_members = ", ".join(
            m.mention
            for m in map(ctx.guild.get_member, vip_member_list)
            if m is not None
        )
        content_roles = ", ".join(
            r.mention for r in map(ctx.guild.get_role, vip_role_list) if r is not None
        )
        pages_members = list(pagify(content_members, page_length=1024))
        pages_roles = list(pagify(content_roles, page_length=1024))
        if not (pages_members or pages_roles):
            await ctx.send("VIP list is empty")
            return
        embed_pages = []
        pages = list(zip_longest(pages_members, pages_roles, fillvalue="None"))
        len_pages = len(pages)
        for idx, page in enumerate(pages, start=1):
            embed = discord.Embed(title="VIP List", colour=await ctx.embed_colour())
            embed.add_field(name="Members", value=page[0])
            embed.add_field(name="Roles", value=page[1])
            embed.set_footer(text="Page {num}/{total}".format(num=idx, total=len_pages))
            embed_pages.append(embed)
        await menus.menu(ctx, embed_pages)

    @vip.command(name="add")
    async def vip_add(self, ctx: GuildContext, *vips: MemberOrRole) -> None:
        """
        Adds members and roles to vip list of VIP module.

        VIP members and roles will not count to user limit in voice channel.
        """
        vip_member_list = await self.config.guild(ctx.guild).vip_member_list()
        vip_role_list = await self.config.guild(ctx.guild).vip_role_list()
        for vip in vips:
            if isinstance(vip, discord.Role):
                vip_list = vip_role_list
            else:
                vip_list = vip_member_list
            if vip.id not in vip_list:
                vip_list.append(vip.id)
            else:
                await ctx.send(f"{vip} is already on list")
        await self.config.guild(ctx.guild).vip_member_list.set(vip_member_list)
        await self.config.guild(ctx.guild).vip_role_list.set(vip_role_list)
        await ctx.send("VIP list updated")

    @vip.command(name="remove")
    async def vip_remove(self, ctx: GuildContext, *vips: MemberOrRole) -> None:
        """
        Removes members and roles to vip list of VIP module.

        VIP members and roles will not count to user limit in voice channel.
        """
        vip_member_list = await self.config.guild(ctx.guild).vip_member_list()
        vip_role_list = await self.config.guild(ctx.guild).vip_role_list()
        for vip in vips:
            if isinstance(vip, discord.Role):
                vip_list = vip_role_list
            else:
                vip_list = vip_member_list
            try:
                vip_list.remove(vip.id)
            except ValueError:
                await ctx.send(f"{vip} is not on list")
        await self.config.guild(ctx.guild).vip_member_list.set(vip_member_list)
        await self.config.guild(ctx.guild).vip_role_list.set(vip_role_list)
        await ctx.send("VIP list updated")

    async def cog_disabled_in_guild(self, guild: Optional[discord.Guild]) -> bool:
        # compatibility layer with Red 3.3.10
        func: Optional[
            Callable[[commands.Cog, Optional[discord.Guild]], Awaitable[bool]]
        ] = getattr(self.bot, "cog_disabled_in_guild", None)
        if func is None:
            return False
        return await func(self, guild)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if await self.cog_disabled_in_guild(member.guild):
            return
        if await self.config.guild(member.guild).vip_enabled():
            if await self._vip_check(member, before, after):
                return
        if await self.config.guild(member.guild).forcelimit_enabled():
            await self._forcelimit_check(member, before, after)

    async def _vip_check(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> bool:
        """
        If VIP joins/leaves a channel with user limit, modify it accordingly.

        Returns True, if user or user's role is VIP
        """
        vip_member_list = await self.config.guild(member.guild).vip_member_list()
        vip_role_list = await self.config.guild(member.guild).vip_role_list()
        if before.channel is not after.channel:
            member_on_list = member.id in vip_member_list
            role_list = [role.id for role in member.roles if role.id in vip_role_list]
            if member_on_list or role_list:
                vip_id = member.id if member_on_list else role_list[0]
                vip_type = "member" if member_on_list else "role"
                before_channel = before.channel
                if before_channel is not None and before_channel.user_limit != 0:
                    await before_channel.edit(
                        user_limit=before_channel.user_limit - 1
                    )  # type: ignore # incorrect overload in d.py
                    channel_id = before_channel.id
                    log.debug(
                        (
                            "VIP with ID %s (%s)"
                            " left voice channel with ID %s, lowering user limit!"
                        ),
                        vip_id,
                        vip_type,
                        channel_id,
                    )
                    return True

                after_channel = after.channel
                if after_channel is not None and after_channel.user_limit != 0:
                    await after_channel.edit(
                        user_limit=after_channel.user_limit + 1
                    )  # type: ignore # incorrect overload in d.py
                    channel_id = after_channel.id
                    log.debug(
                        (
                            "VIP with ID %s (%s)"
                            " joined voice channel with ID %s, raising user limit!"
                        ),
                        vip_id,
                        vip_type,
                        channel_id,
                    )
                    return True
        return False

    async def _forcelimit_check(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """If user joins a channel with user limit, make sure it's not overcrowded."""
        guild_conf = self.config.guild(member.guild)
        ignore_member_list = await guild_conf.forcelimit_ignore_member_list()
        ignore_role_list = await guild_conf.forcelimit_ignore_role_list()
        ignore_vc_list = await guild_conf.forcelimit_ignore_vc_list()
        channel = after.channel
        if (
            channel is not None
            and channel.user_limit != 0
            and len(channel.members) > channel.user_limit
        ):
            if (
                member.id in ignore_member_list
                or any(role.id in ignore_role_list for role in member.roles)
                or channel.id in ignore_vc_list
            ):
                return
            await member.move_to(None)
            log.debug(
                (
                    "Member with ID %s joined voice channel with ID %s"
                    " exceeding its limit, disconnecting!"
                ),
                member.id,
                channel.id,
            )
