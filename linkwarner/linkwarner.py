import logging
from string import Template
from typing import Dict, cast

import discord
from redbot.core import checks, commands, modlog
from redbot.core.bot import Red
from redbot.core.config import Config
from redbot.core.utils.chat_formatting import box
from redbot.core.utils.common_filters import URL_RE

from .data_classes import ChannelData, GuildData


log = logging.getLogger("red.jackcogs.linkwarner")


class LinkWarner(commands.Cog):
    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=176070082584248320, force_registration=True
        )
        self.config.register_guild(
            enabled=False, exclude_roles=[], exclude_domains=[], warn_message=""
        )
        self.config.register_channel(ignore=False, exclude_domains=[], warn_message="")
        self.guild_cache: Dict[int, GuildData] = {}

    async def initialize(self):
        # TODO: possibly load guild data in cache on load?
        try:
            await modlog.register_casetype(
                name="linkwarn",
                default_setting=True,
                image="\N{WARNING SIGN}",
                case_str="Link Warning",
            )
        except RuntimeError:
            pass

    async def get_guild_data(self, guild: discord.Guild) -> GuildData:
        # I wonder what's memory footprint of having all those GuildData objects
        # for the guilds that don't use this cog at all...
        try:
            return self.guild_cache[guild.id]
        except KeyError:
            pass

        guild_settings = await self.config.guild(guild).all()
        data = self.guild_cache[guild.id] = GuildData(guild.id, **guild_settings)
        return data

    async def get_channel_data(self, channel: discord.TextChannel) -> ChannelData:
        guild_data = await self.get_guild_data(channel.guild)
        try:
            return guild_data.channel_cache[channel.id]
        except KeyError:
            pass

        channel_settings = await self.config.channel(channel).all()
        data = ChannelData(channel.id, guild_data=guild_data, **channel_settings)
        guild_data.channel_cache[channel.id] = data

        return data

    @commands.group()
    @checks.admin()
    async def linkwarner(self, ctx: commands.Context) -> None:
        """Settings for LinkWarner cog."""

    @linkwarner.command(name="state")
    async def linkwarner_state(
        self, ctx: commands.Context, enabled: bool = None
    ) -> None:
        """Set if LinkWarner should be enabled for this guild,
        if used without a setting, this will show the current state."""
        guild_data = await self.get_guild_data(ctx.guild)
        if enabled is None:
            if guild_data.enabled:
                message = "Bot filters links in this server."
            else:
                message = "Bot doesn't filter links in this server."
            await ctx.send(message)
            return

        await self.config.guild(ctx.guild).enabled.set(enabled)
        guild_data.update_enabled_state(enabled)

        if enabled:
            message = "Bot will now filter links in this server."
        else:
            message = "Bot will no longer filter links in this server."
        await ctx.send(message)

    @linkwarner.command(name="setmessage")
    async def linkwarner_setmessage(
        self, ctx: commands.Context, *, message: str
    ) -> None:
        """Set link warning message.

        Those fields will get replaced automatically:
        $mention - Mention the user who sent the message with a link
        $username - The user's display name
        $server - The name of the server
        """
        await self.config.guild(ctx.guild).warn_message.set(message)
        guild_data = await self.get_guild_data(ctx.guild)
        guild_data.update_warn_message(message)

        # we've just set the template, it can't be None
        tmpl = cast(Template, guild_data.warn_message_template)
        content = tmpl.safe_substitute(
            mention=ctx.author.mention, username=str(ctx.author), server=ctx.guild.name
        )
        await ctx.send("Link warning message set, sending a test message here...")
        await ctx.send(content)

    @linkwarner.command(name="unsetmessage")
    async def linkwarner_unsetmessage(self, ctx: commands.Context) -> None:
        """Unset link warning message."""
        await self.config.guild(ctx.guild).warn_message.set("")
        guild_data = await self.get_guild_data(ctx.guild)
        guild_data.update_warn_message("")

        await ctx.send("Link warning message unset.")

    # TODO: make this as whitelist/blacklist too

    @linkwarner.group(name="excludedroles")
    async def linkwarner_excludedroles(self, ctx: commands.Context):
        """Settings for roles that are excluded from getting filtered."""

    @linkwarner_excludedroles.command(name="list")
    async def linkwarner_excludedroles_list(self, ctx: commands.Context) -> None:
        """List roles that are excluded from getting filtered."""
        guild_data = await self.get_guild_data(ctx.guild)

        excluded_role_ids = guild_data.exclude_roles
        valid_roles = tuple(r for r in ctx.guild.roles if r.id in excluded_role_ids)
        valid_role_ids = set(r.id for r in valid_roles)
        if excluded_role_ids != valid_role_ids:
            await self.config.guild(ctx.guild).exclude_roles.set(list(valid_role_ids))
            guild_data.update_excluded_roles(valid_role_ids)

        if not valid_roles:
            await ctx.send(
                "There are no roles excluded from link filtering on this server."
            )
            return
        msg = "\n".join(f"+ {r.name}" for r in valid_roles)
        await ctx.send(
            box(f"Roles excluded from link filtering on this server:\n{msg}", "diff")
        )

    @linkwarner_excludedroles.command(name="add")
    async def linkwarner_excludedroles_add(
        self, ctx: commands.Context, *roles: discord.Role
    ) -> None:
        """Add roles that will be excluded from getting filtered."""
        if not roles:
            await ctx.send_help()
            return

        guild_data = await self.get_guild_data(ctx.guild)
        guild_data.add_excluded_roles(role.id for role in roles)
        await self.config.guild(ctx.guild).exclude_roles.set(
            list(guild_data.exclude_roles)
        )

        await ctx.send("Excluded roles updated.")

    @linkwarner_excludedroles.command(name="remove", aliases=["delete"])
    async def linkwarner_excludedroles_remove(
        self, ctx: commands.Context, *roles: discord.Role
    ) -> None:
        """Remove roles that will be excluded from getting filtered."""
        if not roles:
            await ctx.send_help()
            return

        guild_data = await self.get_guild_data(ctx.guild)
        guild_data.remove_excluded_roles(role.id for role in roles)
        await self.config.guild(ctx.guild).exclude_roles.set(
            list(guild_data.exclude_roles)
        )

        await ctx.send("Excluded roles updated.")

    # TODO: change this to support both whitelisting and blacklisting

    @linkwarner.group(name="excludeddomains")
    async def linkwarner_excludeddomains(self, ctx: commands.Context):
        """Settings for domains that are excluded from getting filtered."""

    @linkwarner_excludeddomains.command(name="list")
    async def linkwarner_excludeddomains_list(self, ctx: commands.Context) -> None:
        """List domains that are excluded from getting filtered."""
        guild_data = await self.get_guild_data(ctx.guild)

        excluded_domains = guild_data.exclude_domains
        if not excluded_domains:
            await ctx.send(
                "There are no domains excluded from link filtering on this server."
            )
            return
        msg = "\n".join(f"+ {domain}" for domain in excluded_domains)
        await ctx.send(
            box(f"Domains excluded from link filtering on this server:\n{msg}", "diff")
        )

    @linkwarner_excludeddomains.command(name="add")
    async def linkwarner_excludeddomains_add(
        self, ctx: commands.Context, *domains: str
    ) -> None:
        """Add domains that will be excluded from getting filtered."""
        if not domains:
            await ctx.send_help()
            return

        guild_data = await self.get_guild_data(ctx.guild)
        guild_data.add_excluded_domains(domains)
        await self.config.guild(ctx.guild).exclude_domains.set(
            list(guild_data.exclude_domains)
        )

        await ctx.send("Excluded domains updated.")

    @linkwarner_excludeddomains.command(name="remove", aliases=["delete"])
    async def linkwarner_excludeddomains_remove(
        self, ctx: commands.Context, *domains: str
    ) -> None:
        """Remove domains that will be excluded from getting filtered."""
        if not domains:
            await ctx.send_help()
            return

        guild_data = await self.get_guild_data(ctx.guild)
        guild_data.remove_excluded_domains(domains)
        await self.config.guild(ctx.guild).exclude_domains.set(
            list(guild_data.exclude_domains)
        )

        await ctx.send("Excluded domains updated.")

    # TODO: REMOVE THIS BLOODY HERESY (as in, a lot of unnecessary code repetition)

    @linkwarner.group(name="channel")
    async def linkwarner_channel(self, ctx: commands.Context) -> None:
        """Channel-specific settings for LinkWarner."""

    @linkwarner_channel.command(name="ignore")
    async def linkwarner_channel_ignore(
        self, ctx: commands.Context, channel: discord.TextChannel, ignore: bool = None
    ) -> None:
        """Set if LinkWarner should ignore links in provided channel,
        if used without a setting, this will show the current state."""
        channel_data = await self.get_channel_data(channel)
        if ignore is None:
            if channel_data.ignore:
                message = f"Bot ignores links in {channel.mention} channel."
            else:
                message = f"Bot filters links in {channel.mention} channel."
            await ctx.send(message)
            return

        await self.config.channel(channel).ignore.set(ignore)
        channel_data.update_ignore_state(ignore)

        if ignore:
            message = f"Bot will now ignore links in {channel.mention} channel."
        else:
            message = f"Bot will now filter links in {channel.mention} channel."
        await ctx.send(message)

    @linkwarner_channel.command(name="setmessage")
    async def linkwarner_channel_setmessage(
        self, ctx: commands.Context, channel: discord.TextChannel, *, message: str
    ) -> None:
        """Set link warning message for provided channel.

        Those fields will get replaced automatically:
        $mention - Mention the user who sent the message with a link
        $username - The user's display name
        $server - The name of the server
        """
        await self.config.channel(channel).warn_message.set(message)
        channel_data = await self.get_channel_data(channel)
        channel_data.update_warn_message(message)

        # we've just set the template, it can't be None
        tmpl = cast(Template, channel_data.warn_message_template)
        content = tmpl.safe_substitute(
            mention=ctx.author.mention, username=str(ctx.author), server=ctx.guild.name
        )
        await ctx.send("Link warning message set, sending a test message here...")
        await ctx.send(content)

    @linkwarner_channel.command(name="unsetmessage")
    async def linkwarner_channel_unsetmessage(
        self, ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
        """Unset link warning message for provided channel."""
        await self.config.channel(channel).warn_message.set("")
        channel_data = await self.get_channel_data(channel)
        channel_data.update_warn_message("")

        await ctx.send("Link warning message unset.")

    @linkwarner_channel.group(name="excludeddomains")
    async def linkwarner_channel_excludeddomains(self, ctx: commands.Context):
        """Settings for domains that are excluded from getting filtered."""

    @linkwarner_channel_excludeddomains.command(name="list")
    async def linkwarner_channel_excludeddomains_list(
        self, ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
        """List domains that are excluded from getting filtered in provided channel."""
        channel_data = await self.get_channel_data(channel)

        excluded_domains = channel_data.channel_exclude_domains
        if not excluded_domains:
            await ctx.send(
                "There are no domains excluded from link filtering on this channel"
                " (doesn't include domains excluded from filtering in whole guild)."
            )
            return
        msg = "\n".join(f"+ {domain}" for domain in excluded_domains)
        await ctx.send(
            box(
                f"Domains excluded from link filtering on #{channel.name} channel"
                " (doesn't include domains excluded from filtering in whole guild):\n"
                f"{msg}",
                "diff",
            )
        )

    @linkwarner_channel_excludeddomains.command(name="add")
    async def linkwarner_channel_excludeddomains_add(
        self, ctx: commands.Context, channel: discord.TextChannel, *domains: str
    ) -> None:
        """Add domains that will be excluded
        from getting filtered in provided channel.
        """
        if not domains:
            await ctx.send_help()
            return

        channel_data = await self.get_channel_data(channel)
        channel_data.add_excluded_domains(domains)
        await self.config.channel(channel).exclude_domains.set(
            list(channel_data.channel_exclude_domains)
        )

        await ctx.send("Excluded domains updated.")

    @linkwarner_channel_excludeddomains.command(name="remove", aliases=["delete"])
    async def linkwarner_channel_excludeddomains_remove(
        self, ctx: commands.Context, channel: discord.TextChannel, *domains: str
    ) -> None:
        """Remove domains that will be excluded
        from getting filtered in provided channel.
        """
        if not domains:
            await ctx.send_help()
            return

        channel_data = await self.get_channel_data(channel)
        channel_data.remove_excluded_domains(domains)
        await self.config.channel(channel).exclude_domains.set(
            list(channel_data.channel_exclude_domains)
        )

        await ctx.send("Excluded domains updated.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        guild = message.guild
        if guild is None or message.author.bot:
            return
        # casting with the knowledge we got above
        author = cast(discord.Member, message.author)
        channel = cast(discord.TextChannel, message.channel)
        if await self.bot.is_automod_immune(message):
            return

        channel_data = await self.get_channel_data(channel)
        guild_data = channel_data.guild_data
        if not channel_data.enabled:
            return

        common_roles = guild_data.exclude_roles.intersection(
            role.id for role in author.roles
        )
        if common_roles:
            return

        for match in URL_RE.finditer(message.content):
            address = match.group(2)
            domains_filter = channel_data.domains_filter
            if domains_filter is not None and domains_filter.match(address):
                continue

            try:
                await message.delete()
            except discord.Forbidden:
                log.error(
                    "Bot can't delete messages in channel with ID %s (guild ID: %s)",
                    channel.id,
                    guild.id,
                )
            template = channel_data.warn_message_template
            if template is None:
                return

            try:
                await channel.send(
                    template.safe_substitute(
                        mention=author.mention, username=str(author), server=guild.name
                    )
                )
            except discord.Forbidden:
                log.error(
                    "Bot can't send messages in channel with ID %s (guild ID: %s)",
                    channel.id,
                    guild.id,
                )
            await modlog.create_case(
                bot=self.bot,
                guild=guild,
                created_at=message.created_at,
                action_type="linkwarn",
                user=author,
                moderator=guild.me,
                reason=f"Warned for posting a link - {match.group(0)}",
                channel=message.channel,
            )
            return
