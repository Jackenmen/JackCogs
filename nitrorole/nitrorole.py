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
import logging
import random
from typing import Any, Awaitable, Callable, Dict, Literal, Union, cast

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands import GuildContext, NoParseOptional as Optional
from redbot.core.config import Config
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.utils.predicates import MessagePredicate

from .guild_data import GuildData

log = logging.getLogger("red.jackcogs.nitrorole")

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]


class NitroRole(commands.Cog):
    """Welcome new nitro boosters and/or give them a special role!"""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=176070082584248320, force_registration=True
        )
        self.config.register_guild(
            role_id=None,
            channel_id=None,
            message_templates=[],
            unassign_on_boost_end=False,
        )
        self.message_images = cog_data_path(self) / "message_images"
        self.message_images.mkdir(parents=True, exist_ok=True)
        self.guild_cache: Dict[int, GuildData] = {}
        # TODO: possibly load guild data in cache on load?

    async def red_get_data_for_user(self, *, user_id: int) -> Dict[str, Any]:
        # this cog does not story any data
        return {}

    async def red_delete_data_for_user(
        self, *, requester: RequestType, user_id: int
    ) -> None:
        # this cog does not story any data
        pass

    async def get_guild_data(self, guild: discord.Guild) -> GuildData:
        try:
            return self.guild_cache[guild.id]
        except KeyError:
            pass

        guild_settings = await self.config.guild(guild).all()
        data = self.guild_cache[guild.id] = GuildData(
            guild.id, self.config, **guild_settings
        )
        return data

    @commands.guild_only()
    @commands.admin_or_permissions(manage_roles=True)
    @commands.group()
    async def nitrorole(self, ctx: GuildContext) -> None:
        """Settings for NitroRole cog."""

    @nitrorole.command(name="unassignonboostend")
    async def nitrorole_unassign_on_boost_end(
        self, ctx: GuildContext, enabled: Optional[bool] = None
    ) -> None:
        """
        Set if booster role should be unassigned when someone stops boosting server.

        Leave empty to see current settings.
        """
        guild = ctx.guild
        guild_data = await self.get_guild_data(guild)
        if enabled is None:
            if guild_data.unassign_on_boost_end:
                message = (
                    "Bot unassigns booster role when user stops boosting the server."
                )
            else:
                message = (
                    "Bot doesn't unassign booster role"
                    " when user stops boosting the server."
                )
            await ctx.send(message)
            return

        await guild_data.set_unassign_on_boost_end(enabled)

        if enabled:
            message = (
                "Bot will now unassign booster role"
                " when user stops boosting the server."
            )
        else:
            message = (
                "Bot will no longer unassign booster role"
                " when user stops boosting the server."
            )
        await ctx.send(message)

    @nitrorole.command(name="autoassignrole")
    async def nitrorole_autoassignrole(
        self, ctx: GuildContext, *, role: Optional[discord.Role] = None
    ) -> None:
        """
        Set role that will be autoassigned after someone boosts server.

        Leave empty to not assign any role.
        """
        guild = ctx.guild
        guild_data = await self.get_guild_data(guild)
        if role is None:
            await guild_data.set_role(None)
            await ctx.send(
                "Role will not be autoassigned anymore when someone boosts server."
            )
            return
        if (
            guild.owner_id != ctx.author.id
            and role > ctx.author.top_role
            and not await self.bot.is_owner(ctx.author)
        ):
            await ctx.send("You can't use a role that is above your top role!")
            return

        await guild_data.set_role(role)
        await ctx.send(f"Nitro boosters will now be assigned {role.name} role.")

    @nitrorole.command(name="channel")
    async def nitrorole_channel(
        self,
        ctx: GuildContext,
        channel: Optional[
            Union[discord.TextChannel, discord.VoiceChannel, discord.StageChannel]
        ] = None,
    ) -> None:
        """Set channel for new booster messages. Leave empty to disable."""
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.set_channel(channel)
        if channel is None:
            await ctx.send("New booster messages disabled.")
            return
        await ctx.send(f"New booster messages will now be sent in {channel.mention}")

    @nitrorole.command(name="addmessage")
    async def nitrorole_addmessage(self, ctx: GuildContext, *, message: str) -> None:
        """
        Add new booster message.

        Those fields will get replaced automatically:
        $mention - Mention the user who boosted
        $username - The user's display name
        $server - The name of the server
        $count - The number of boosts server has
        (this isn't the same as amount of users that boost this server)
        $plural - Empty if count is 1. 's' otherwise

        Note: New booster message can also have image.
        To set it, use `[p]nitrorole setimage`
        """
        guild = ctx.guild
        guild_data = await self.get_guild_data(guild)
        template = await guild_data.add_message(message)
        content = template.safe_substitute(
            mention=ctx.author.mention,
            username=ctx.author.display_name,
            server=guild.name,
            count="2",
            plural="s",
        )

        filename = next(self.message_images.glob(f"{guild.id}.*"), None)
        file = None
        warning = ""
        if filename is not None:
            channel_id = guild_data.channel_id
            channel = guild.get_channel(channel_id) if channel_id is not None else None
            if (
                channel is not None
                and not channel.permissions_for(guild.me).attach_files
            ):
                warning = (
                    "WARNING: Bot doesn't have permissions to send images"
                    " in channel used for new booster messages.\n\n"
                )

            if not ctx.channel.permissions_for(guild.me).attach_files:
                await ctx.send(
                    f"{warning}New booster message set.\n"
                    "I wasn't able to send test message here"
                    ' due to missing "Attach files" permission.'
                )
                return

            file = discord.File(str(filename))
        await ctx.send(
            f"{warning}New booster message set, sending a test message here..."
        )
        await ctx.send(content, file=file)

    @nitrorole.command(name="removemessage", aliases=["deletemessage"])
    async def nitrorole_removemessage(self, ctx: GuildContext) -> None:
        """Remove new booster message."""
        guild_data = await self.get_guild_data(ctx.guild)
        if not guild_data.messages:
            await ctx.send("This guild doesn't have any new booster message set.")
            return

        msg = "Choose a new booster message to delete:\n\n"
        for idx, template in enumerate(guild_data.messages, 1):
            msg += f"  {idx}. {template}\n"
        for page in pagify(msg):
            await ctx.send(box(page))

        pred = MessagePredicate.valid_int(ctx)

        try:
            await self.bot.wait_for(
                "message",
                check=lambda m: pred(m) and cast(int, pred.result) >= 1,
                timeout=30,
            )
        except asyncio.TimeoutError:
            await ctx.send("Okay, no messages will be removed.")
            return

        result = cast(int, pred.result)
        try:
            await guild_data.remove_message(result - 1)
        except IndexError:
            await ctx.send("Wow! That's a big number. Too big...")
            return
        await ctx.send("Message removed.")

    @nitrorole.command(name="listmessages")
    async def nitrorole_listmessages(self, ctx: GuildContext) -> None:
        """List new booster message templates."""
        guild_data = await self.get_guild_data(ctx.guild)
        if not guild_data.messages:
            await ctx.send(
                "This guild doesn't have any new booster message templates set."
            )
            return

        msg = "New booster message templates:\n\n"
        for idx, template in enumerate(guild_data.messages, 1):
            msg += f"  {idx}. {template}\n"
        for page in pagify(msg):
            await ctx.send(box(page))

    @nitrorole.command(name="setimage")
    async def nitrorole_setimage(self, ctx: GuildContext) -> None:
        """Set image for new booster message."""
        guild = ctx.guild
        if len(ctx.message.attachments) != 1:
            await ctx.send("You have to send exactly one attachment.")
            return

        a = ctx.message.attachments[0]
        if a.width is None:
            await ctx.send("The attachment has to be an image.")
            return

        ext = a.url.rpartition(".")[2]
        filename = self.message_images / f"{ctx.guild.id}.{ext}"
        with open(filename, "wb") as fp:
            await a.save(fp)

        for file in self.message_images.glob(f"{ctx.guild.id}.*"):
            if not file == filename:
                file.unlink()

        guild_data = await self.get_guild_data(guild)
        channel_id = guild_data.channel_id
        channel = guild.get_channel(channel_id) if channel_id is not None else None
        if channel is not None and not channel.permissions_for(guild.me).attach_files:
            await ctx.send(
                "WARNING: Bot doesn't have permissions to send images"
                " in channel used for new booster messages.\n\nImage set."
            )
        else:
            await ctx.send("Image set.")

    @nitrorole.command(name="unsetimage")
    async def nitrorole_unsetimage(self, ctx: GuildContext) -> None:
        """Unset image for new booster message."""
        for file in self.message_images.glob(f"{ctx.guild.id}.*"):
            file.unlink()
        await ctx.send("Image unset.")

    async def cog_disabled_in_guild(self, guild: Optional[discord.Guild]) -> bool:
        # compatibility layer with Red 3.3.10
        func: Optional[
            Callable[[commands.Cog, Optional[discord.Guild]], Awaitable[bool]]
        ] = getattr(self.bot, "cog_disabled_in_guild", None)
        if func is None:
            return False
        return await func(self, guild)

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        if before.premium_since == after.premium_since:
            return

        if await self.cog_disabled_in_guild(after.guild):
            return

        guild_data = await self.get_guild_data(after.guild)

        if before.premium_since is None and after.premium_since is not None:
            await self.maybe_assign_role(guild_data, after)
            await self.maybe_announce(guild_data, after)
        else:
            await self.maybe_unassign_role(guild_data, after)

    def get_role_to_assign(
        self, guild: discord.Guild, guild_data: GuildData
    ) -> Optional[discord.Role]:
        role_id = guild_data.role_id
        if role_id is None:
            return None
        role = guild.get_role(role_id)
        if role is None:
            log.error(
                "Role with ID %s can't be found in guild with ID %s.", role_id, guild.id
            )
            return None
        if role >= guild.me.top_role:
            log.error(
                "Role with ID %s (guild ID: %s) is higher in hierarchy"
                " than any bot's role.",
                role_id,
                guild.id,
            )
            return None
        return role

    async def maybe_assign_role(
        self, guild_data: GuildData, member: discord.Member
    ) -> None:
        role = self.get_role_to_assign(member.guild, guild_data)
        if role is None:
            return
        if member.get_role(role.id) is not None:
            return
        try:
            await member.add_roles(role, reason="New nitro booster - role assigned.")
        except discord.Forbidden:
            log.error(
                "Bot was unable to add role"
                " with ID %s (guild ID: %s) to member with ID %s.",
                role.id,
                role.guild.id,
                member.id,
            )

    async def maybe_unassign_role(
        self, guild_data: GuildData, member: discord.Member
    ) -> None:
        if not guild_data.unassign_on_boost_end:
            return
        role = self.get_role_to_assign(member.guild, guild_data)
        if role is None:
            return
        if member.get_role(role.id) is None:
            return
        try:
            await member.remove_roles(
                role, reason="No longer nitro booster - role unassigned"
            )
        except discord.Forbidden:
            log.error(
                "Bot was unable to remove role"
                " with ID %s (guild ID: %s) from member with ID %s.",
                role.id,
                role.guild.id,
                member.id,
            )

    async def maybe_announce(
        self, guild_data: GuildData, member: discord.Member
    ) -> None:
        channel_id = guild_data.channel_id
        if channel_id is None:
            return
        guild = member.guild
        channel = cast(
            Optional[
                Union[discord.TextChannel, discord.VoiceChannel, discord.StageChannel]
            ],
            guild.get_channel(channel_id),
        )
        if channel is None:
            log.error(
                "Channel with ID %s can't be found in guild with ID %s.",
                channel_id,
                guild.id,
            )
            return

        message_templates = guild_data.message_templates
        if not message_templates:
            return

        filename = next(self.message_images.glob(f"{guild.id}.*"), None)
        file = discord.utils.MISSING
        if filename is not None:
            if channel.permissions_for(guild.me).attach_files:
                file = discord.File(str(filename))
            else:
                log.info(
                    'Bot doesn\'t have "Attach files"'
                    " in channel with ID %s (guild ID: %s)",
                    channel_id,
                    guild.id,
                )
        count = guild.premium_subscription_count
        template = random.choice(message_templates)
        content = template.safe_substitute(
            mention=member.mention,
            username=member.display_name,
            server=guild.name,
            count=str(count),
            plural="" if count == 1 else "s",
        )
        try:
            await channel.send(content, file=file)
        except discord.Forbidden:
            log.error(
                "Bot can't send messages in channel with ID %s (guild ID: %s)",
                channel_id,
                guild.id,
            )
            return
