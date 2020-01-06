import asyncio
import logging
import random
from string import Template
from typing import Iterable, Optional, cast

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.config import Config
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.utils.predicates import MessagePredicate

log = logging.getLogger("red.jackcogs.nitrorole")


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

    @commands.group()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_roles=True)
    async def nitrorole(self, ctx: commands.Context) -> None:
        """Settings for NitroRole cog."""

    @nitrorole.command(name="unassignonboostend")
    async def nitrorole_unassign_on_boost_end(
        self, ctx: commands.Context, enabled: bool = None
    ) -> None:
        """
        Set if booster role should be unassigned when someone stops boosting server.

        Leave empty to see current settings.
        """
        config_value = self.config.guild(ctx.guild).unassign_on_boost_end
        if enabled is None:
            if await config_value():
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

        await config_value.set(enabled)

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
        self, ctx: commands.Context, role: discord.Role = None
    ) -> None:
        """
        Set role that will be autoassigned after someone boosts server.

        Leave empty to not assign any role.
        """
        if role is None:
            await self.config.guild(ctx.guild).role_id.set(None)
            await ctx.send(
                "Role will not be autoassigned anymore when someone boosts server."
            )
            return
        if (
            ctx.guild.owner_id != ctx.author.id
            and role > ctx.author.top_role
            and not await self.bot.is_owner(ctx.author)
        ):
            await ctx.send("You can't use a role that is above your top role!")
            return

        await self.config.guild(ctx.guild).role_id.set(role.id)
        await ctx.send(f"Nitro boosters will now be assigned {role.name} role.")

    @nitrorole.command(name="channel")
    async def nitrorole_channel(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ) -> None:
        """Set channel for new boost messages. Leave empty to disable."""
        if channel is None:
            await self.config.guild(ctx.guild).channel_id.clear()
            await ctx.send("New booster messages disabled.")
            return
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"New booster messages will now be sent in {channel.mention}")

    @nitrorole.command(name="addmessage")
    async def nitrorole_addmessage(
        self, ctx: commands.Context, *, message: str
    ) -> None:
        """
        Add new boost message.

        Those fields will get replaced automatically:
        $mention - Mention the user who boosted
        $username - The user's display name
        $server - The name of the server
        $count - The number of boosts server has
        (this isn't the same as amount of users that boost this server)
        $plural - Empty if count is 1. 's' otherwise

        Note: New boost message can also have image.
        To set it, use `[p]nitrorole setimage`
        """
        guild = ctx.guild
        async with self.config.guild(guild).all() as guild_settings:
            guild_settings["message_templates"].append(message)
        content = Template(message).safe_substitute(
            mention=ctx.author.mention,
            username=ctx.author.display_name,
            server=guild.name,
            count="2",
            plural="s",
        )

        filename = next(self.message_images.glob(f"{guild.id}.*"), None)
        file = discord.File(filename) if filename is not None else None
        if filename is not None:
            channel_id = guild_settings["channel_id"]
            channel = guild.get_channel(channel_id) if channel_id is not None else None
            if (
                channel is not None
                and not channel.permissions_for(guild.me).attach_files
            ):
                message = (
                    "WARNING: Bot doesn't have permissions to send images"
                    " in channel used for new boost messages.\n\n"
                )

            if not ctx.channel.permissions_for(guild.me).attach_files:
                await ctx.send(
                    f"{message}New booster message set.\n"
                    "I wasn't able to send test message here"
                    ' due to missing "Attach files" permission.'
                )
                return

            file = discord.File(filename)
        await ctx.send(
            f"{message}New booster message set, sending a test message here..."
        )
        await ctx.send(content, file=file)

    @nitrorole.command(name="removemessage")
    async def nitrorole_removemessage(self, ctx: commands.Context) -> None:
        """Remove new boost message."""
        templates = await self.config.guild(ctx.guild).message_templates()
        if not templates:
            await ctx.send("This guild doesn't have any new boost message set.")
            return

        msg = "Choose a new boost message to delete:\n\n"
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

    @nitrorole.command(name="setimage")
    async def nitrorole_setimage(self, ctx: commands.Context) -> None:
        """Set image for new boost message."""
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
                " in channel used for new boost messages.\n\nImage set."
            )
        else:
            await ctx.send("Image set.")

    @nitrorole.command(name="unsetimage")
    async def nitrorole_unsetimage(self, ctx: commands.Context) -> None:
        """Unset image for new boost message."""
        for file in self.message_images.glob(f"{ctx.guild.id}.*"):
            file.unlink()
        await ctx.send("Image unset.")

    @commands.Cog.listener()
    async def on_guild_update(
        self, before: discord.Guild, after: discord.Guild
    ) -> None:
        before_subs = set(before.premium_subscribers)
        after_subs = set(after.premium_subscribers)
        if before_subs != after_subs:
            added = after_subs - before_subs
            removed = before_subs - after_subs
            settings = await self.config.guild(after).all()
            await self.handle_roles(after, added, removed, settings)
            await self.maybe_announce(after, added, settings)

    async def handle_roles(
        self,
        guild: discord.Guild,
        added: Iterable[discord.Member],
        removed: Iterable[discord.Member],
        settings: dict,
    ) -> None:
        role_id = settings["role_id"]
        if role_id is None:
            return
        role = guild.get_role(role_id)
        if role is None:
            log.error(
                "Role with ID %s can't be found in guild with ID %s.", role_id, guild.id
            )
            return
        if role >= guild.me.top_role:
            log.error(
                "Role with ID %s (guild ID: %s) is higher in hierarchy"
                " than any bot's role.",
                role_id,
                guild.id,
            )
            return
        await self.maybe_assign_role(role, added)
        if settings["unassign_on_boost_end"]:
            await self.maybe_unassign_role(role, removed)

    async def maybe_assign_role(
        self, role: discord.Role, members: Iterable[discord.Member]
    ) -> None:
        for member in members:
            if role in member.roles:
                return
            try:
                await member.add_roles(
                    role, reason="New nitro booster - role assigned."
                )
            except discord.Forbidden:
                log.error(
                    "Bot was unable to add role"
                    " with ID %s (guild ID: %s) to member with ID %s.",
                    role.id,
                    role.guild.id,
                    member.id,
                )

    async def maybe_unassign_role(
        self, role: discord.Role, members: Iterable[discord.Member]
    ) -> None:
        for member in members:
            if role not in member.roles:
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
        self, guild: discord.Guild, members: Iterable[discord.Member], settings: dict
    ) -> None:
        channel_id = settings["channel_id"]
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

        message_templates = settings["message_templates"]
        if not message_templates:
            return

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
        count = guild.premium_subscription_count
        for member in members:
            message_template = random.choice(message_templates)
            content = Template(message_template).safe_substitute(
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
