import asyncio
import logging
import random
from string import Template
from typing import Optional, Union, cast

import discord
from redbot.core import commands, checks
from redbot.core.bot import Red
from redbot.core.config import Config
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.utils.predicates import MessagePredicate


log = logging.getLogger("red.jackcogs.banmessage")


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

    @commands.group()
    @commands.guild_only()
    @checks.admin()
    async def banmessageset(self, ctx: commands.Context) -> None:
        """BanMessage settings."""

    @banmessageset.command(name="hackban")
    async def banmessageset_hackban(
        self, ctx: commands.Context, enabled: bool = None
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
        self, ctx: commands.Context, channel: discord.TextChannel = None
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
        self, ctx: commands.Context, *, message: str
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
        message = ""
        if filename is not None:
            channel_id = guild_settings["channel"]
            channel = guild.get_channel(channel_id) if channel_id is not None else None
            if (
                channel is not None
                and not channel.permissions_for(guild.me).attach_files
            ):
                message = (
                    "WARNING: Bot doesn't have permissions to send images"
                    " in channel used for ban messages.\n\n"
                )

            if not ctx.channel.permissions_for(guild.me).attach_files:
                await ctx.send(
                    f"{message}Ban message set.\n"
                    "I wasn't able to send test message here"
                    ' due to missing "Attach files" permission.'
                )
                return

            file = discord.File(filename)
        await ctx.send(f"{message}Ban message set, sending a test message here...")
        await ctx.send(content, file=file)

    @banmessageset.command(name="removemessage")
    async def banmessageset_removemessage(self, ctx: commands.Context) -> None:
        """Remove ban message."""
        templates = await self.config.guild(ctx.guild).message_templates()
        if not templates:
            await ctx.send("This guild doesn't have any ban message set.")
            return

        msg = "Choose a ban message to delete:\n\n"
        for idx, template in enumerate(templates):
            msg += f"  {idx}. {template}\n"
        for page in pagify(msg):
            await ctx.send(box(page))

        pred = MessagePredicate.valid_int(ctx)
        try:
            await self.bot.wait_for(
                "message", check=lambda m: pred(m) and pred.result >= 0, timeout=30
            )
        except asyncio.TimeoutError:
            await ctx.send("Okay, no messages will be removed.")
            return
        try:
            templates.pop(pred.result)
        except IndexError:
            await ctx.send("Wow! That's a big number. Too big...")
            return
        await self.config.guild(ctx.guild).message_templates.set(templates)
        await ctx.send("Message removed.")

    @banmessageset.command(name="setimage")
    async def banmessageset_setimage(self, ctx: commands.Context) -> None:
        """Set image for ban message."""
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
    async def banmessageset_unsetimage(self, ctx: commands.Context) -> None:
        """Unset image for ban message."""
        for file in self.message_images.glob(f"{ctx.guild.id}.*"):
            file.unlink()
        await ctx.send("Image unset.")

    @commands.Cog.listener()
    async def on_member_ban(
        self, guild: discord.Guild, user: Union[discord.User, discord.Member]
    ) -> None:
        # TODO: add caching to prevent a lot of fetches when mass-banning users
        settings = await self.config.guild(guild).all()
        channel_id = settings["channel"]
        if channel_id is None:
            return
        channel = cast(Optional[discord.TextChannel], guild.get_channel(channel_id))
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
        file = None
        if filename is not None:
            if channel.permissions_for(guild.me).attach_files:
                file = discord.File(filename)
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
