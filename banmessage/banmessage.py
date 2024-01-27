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
from string import Template
from typing import Any, Awaitable, Callable, Dict, Literal, Union, cast

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands import GuildContext, NoParseOptional as Optional
from redbot.core.config import Config
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.utils.predicates import MessagePredicate

log = logging.getLogger("red.jackcogs.banmessage")

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]


class BanMessage(commands.Cog):
    """Send message on ban in a chosen channel. Supports images!"""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=176070082584248320, force_registration=True
        )
        self.config.register_guild(channel=None, hackban=True, message_templates=[])
        self.message_images = cog_data_path(self) / "message_images"
        self.message_images.mkdir(exist_ok=True)

    async def red_get_data_for_user(self, *, user_id: int) -> Dict[str, Any]:
        # this cog does not story any data
        return {}

    async def red_delete_data_for_user(
        self, *, requester: RequestType, user_id: int
    ) -> None:
        # this cog does not story any data
        pass

    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.group()
    async def banmessageset(self, ctx: GuildContext) -> None:
        """BanMessage settings."""

    @banmessageset.command(name="hackban")
    async def banmessageset_hackban(
        self, ctx: GuildContext, enabled: Optional[bool] = None
    ) -> None:
        """
        Set if hackbans should trigger ban messages.

        INFO: Hackbans are bans of users
        that weren't members of the guild (also called preemptive bans).
        """
        config_value = self.config.guild(ctx.guild).hackban
        if enabled is None:
            if await config_value():
                message = "Hackbans trigger ban messages in this server."
            else:
                message = "Hackbans don't trigger ban messages in this server."
            await ctx.send(message)
            return

        await config_value.set(enabled)

        if enabled:
            message = "Hackbans will now trigger ban messages in this server."
        else:
            message = "Hackbans will no longer trigger ban messages in this server."
        await ctx.send(message)

    @banmessageset.command(name="channel")
    async def banmessageset_channel(
        self,
        ctx: GuildContext,
        channel: Optional[
            Union[discord.TextChannel, discord.VoiceChannel, discord.StageChannel]
        ] = None,
    ) -> None:
        """Set channel for ban messages. Leave empty to disable."""
        if channel is None:
            await self.config.guild(ctx.guild).channel.clear()
            await ctx.send("Ban messages are now disabled.")
            return
        await self.config.guild(ctx.guild).channel.set(channel.id)
        await ctx.send(f"Ban messages will now be sent in {channel.mention}")

    @banmessageset.command(name="addmessage")
    async def banmessageset_addmessage(
        self, ctx: GuildContext, *, message: str
    ) -> None:
        """
        Add ban message.

        Those fields will get replaced automatically:
        $username - The banned user's name
        $server - The name of the server

        Note: Ban message can also have image.
        To set it, use `[p]banmessageset setimage`
        """
        guild = ctx.guild
        async with self.config.guild(guild).all() as guild_settings:
            guild_settings["message_templates"].append(message)
        content = Template(message).safe_substitute(
            username=str(ctx.author), server=guild.name
        )

        filename = next(self.message_images.glob(f"{guild.id}.*"), None)
        file = None
        warning = ""
        if filename is not None:
            channel_id = guild_settings["channel"]
            channel = guild.get_channel(channel_id) if channel_id is not None else None
            if (
                channel is not None
                and not channel.permissions_for(guild.me).attach_files
            ):
                warning = (
                    "WARNING: Bot doesn't have permissions to send images"
                    " in channel used for ban messages.\n\n"
                )

            if not ctx.channel.permissions_for(guild.me).attach_files:
                await ctx.send(
                    f"{warning}Ban message set.\n"
                    "I wasn't able to send test message here"
                    ' due to missing "Attach files" permission.'
                )
                return

            file = discord.File(str(filename))
        await ctx.send(f"{warning}Ban message set, sending a test message here...")
        await ctx.send(content, file=file)

    @banmessageset.command(name="removemessage", aliases=["deletemessage"])
    async def banmessageset_removemessage(self, ctx: GuildContext) -> None:
        """Remove ban message."""
        templates = await self.config.guild(ctx.guild).message_templates()
        if not templates:
            await ctx.send("This guild doesn't have any ban message set.")
            return

        msg = "Choose a ban message to delete:\n\n"
        for idx, template in enumerate(templates, 1):
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
            templates.pop(result - 1)
        except IndexError:
            await ctx.send("Wow! That's a big number. Too big...")
            return
        await self.config.guild(ctx.guild).message_templates.set(templates)
        await ctx.send("Message removed.")

    @banmessageset.command(name="listmessages")
    async def banmessageset_listmessages(self, ctx: GuildContext) -> None:
        """List ban message templates."""
        templates = await self.config.guild(ctx.guild).message_templates()
        if not templates:
            await ctx.send("This guild doesn't have any ban message templates set.")
            return

        msg = "Ban message templates:\n\n"
        for idx, template in enumerate(templates, 1):
            msg += f"  {idx}. {template}\n"
        for page in pagify(msg):
            await ctx.send(box(page))

    @banmessageset.command(name="setimage")
    async def banmessageset_setimage(self, ctx: GuildContext) -> None:
        """Set image for ban message."""
        guild = ctx.guild
        if len(ctx.message.attachments) != 1:
            await ctx.send("You have to send exactly one attachment.")
            return

        a = ctx.message.attachments[0]
        if a.width is None:
            await ctx.send("The attachment has to be an image.")
            return

        ext = a.filename.rpartition(".")[2]
        filename = self.message_images / f"{ctx.guild.id}.{ext}"
        with open(filename, "wb") as fp:
            await a.save(fp)

        for file in self.message_images.glob(f"{ctx.guild.id}.*"):
            if not file == filename:
                file.unlink()

        channel_id = await self.config.guild(guild).channel()
        channel = guild.get_channel(channel_id) if channel_id is not None else None
        if channel is not None and not channel.permissions_for(guild.me).attach_files:
            await ctx.send(
                "WARNING: Bot doesn't have permissions to send images"
                " in channel used for ban messages.\n\nImage set."
            )
        else:
            await ctx.send("Image set.")

    @banmessageset.command(name="unsetimage")
    async def banmessageset_unsetimage(self, ctx: GuildContext) -> None:
        """Unset image for ban message."""
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
    async def on_member_ban(
        self, guild: discord.Guild, user: Union[discord.User, discord.Member]
    ) -> None:
        if await self.cog_disabled_in_guild(guild):
            return
        # TODO: add caching to prevent a lot of fetches when mass-banning users
        settings = await self.config.guild(guild).all()
        channel_id = settings["channel"]
        if channel_id is None:
            return
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
        if not settings["hackban"] and not hasattr(user, "guild"):
            return

        message_templates = settings["message_templates"]
        if not message_templates:
            return
        message_template = random.choice(message_templates)

        content = Template(message_template).safe_substitute(
            username=str(user), server=guild.name
        )
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
        try:
            await channel.send(content, file=file)
        except discord.Forbidden:
            log.error(
                "Bot can't send messages in channel with ID %s (guild ID: %s)",
                channel_id,
                guild.id,
            )
