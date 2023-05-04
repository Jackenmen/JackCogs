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
from typing import Any, Dict, Literal, Union

import discord
from redbot.core import commands, modlog
from redbot.core.bot import Red
from redbot.core.commands import GuildContext
from redbot.core.config import Config
from redbot.core.utils import can_user_send_messages_in
from redbot.core.utils.chat_formatting import humanize_list, inline
from redbot.core.utils.common_filters import URL_RE

from .converters import DomainName
from .data_classes import (
    ChannelData,
    ConfigurableChannel,
    DomainsMode,
    GuildData,
    GuildDomainsMode,
)

log = logging.getLogger("red.jackcogs.linkwarner")

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]


class LinkWarner(commands.Cog):
    """Remove messages containing links and warn users for it."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=176070082584248321, force_registration=True
        )
        self.config.register_guild(
            enabled=False,
            check_edits=True,
            use_dms=False,
            delete_delay=None,
            excluded_roles=[],
            domains_mode=DomainsMode.ALLOW_FROM_SCOPE_LIST.value,
            domains_list=[],
            warn_message="",
        )
        self.config.register_channel(
            ignored=False,
            domains_mode=DomainsMode.INHERIT_MODE_AND_UNION_LISTS.value,
            domains_list=[],
            warn_message="",
        )
        self.guild_cache: Dict[int, GuildData] = {}

    async def cog_load(self) -> None:
        try:
            await modlog.register_casetype(
                name="linkwarn",
                default_setting=True,
                image="\N{WARNING SIGN}",
                case_str="Link Warning",
            )
        except RuntimeError:
            pass

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

        data = await GuildData.from_guild(self.config, guild)
        self.guild_cache[guild.id] = data

        return data

    async def get_channel_data(
        self, channel: Union[ConfigurableChannel, discord.Thread]
    ) -> ChannelData:
        guild_data = await self.get_guild_data(channel.guild)
        if isinstance(channel, discord.Thread):
            if channel.parent is None:
                raise RuntimeError("The parent channel of the thread is unknown.")
            channel = channel.parent
        return await guild_data.get_channel_data(channel)

    @commands.admin()
    @commands.guild_only()
    @commands.group()
    async def linkwarner(self, ctx: GuildContext) -> None:
        """Settings for LinkWarner cog."""

    @linkwarner.command(name="showsettings")
    async def linkwarner_showsettings(self, ctx: GuildContext) -> None:
        """Show settings for the current guild."""
        guild_data = await self.get_guild_data(ctx.guild)
        enabled = "Yes" if guild_data.enabled else "No"
        use_dms = "Yes" if guild_data.use_dms else "No"
        delete_delay = guild_data.delete_delay
        auto_deletion = f"After {delete_delay} seconds" if delete_delay else "Disabled"
        excluded_roles = (
            humanize_list(
                [
                    r.mention
                    for r in ctx.guild.roles
                    if r.id in guild_data.excluded_roles
                ]
            )
            or "*None*"
        )
        domains_mode = (
            "Only allow domains from the domains list"
            if guild_data.domains_mode is DomainsMode.ALLOW_FROM_SCOPE_LIST
            else "Allow all domains except the domains from the domains list"
        )
        # purposefully not using humanize_list() here to avoid confusion
        domains_list = ", ".join(guild_data.domains_list) or "*Empty*"
        await ctx.send(
            "**LinkWarner's Guild Settings**\n\n"
            ">>> "
            f"**Enabled:** {enabled}\n"
            f"**Send warning message in DMs:** {use_dms}\n"
            f"**Auto-deletion of warning messages:** {auto_deletion}\n"
            f"**Excluded roles:** {excluded_roles}\n"
            f"**Domains list mode:** {domains_mode}\n"
            f"**Domains list:** {domains_list}"
        )

    @linkwarner.group(name="channel")
    async def linkwarner_channel(self, ctx: GuildContext) -> None:
        """Channel-specific settings for LinkWarner."""

    @linkwarner_channel.command(name="showsettings")
    async def linkwarner_channel_showsettings(
        self, ctx: GuildContext, channel: ConfigurableChannel
    ) -> None:
        """Show settings for the given channel."""
        channel_data = await self.get_channel_data(channel)
        guild_data = channel_data.guild_data
        ignored = "Yes" if channel_data.ignored else "No"
        if channel_data.domains_mode is DomainsMode.ALLOW_FROM_SCOPE_LIST:
            domains_mode = "Only allow domains from the channel's domains list"
        elif channel_data.domains_mode is DomainsMode.DISALLOW_FROM_SCOPE_LIST:
            domains_mode = (
                "Allow all domains except the domains from the channel's domains list"
            )
        else:
            if guild_data.domains_mode is DomainsMode.ALLOW_FROM_SCOPE_LIST:
                domains_mode = (
                    "Only allow domains from the guild's and channel's domains list"
                )
            else:
                domains_mode = (
                    "Allow all domains except the domains"
                    " from the guild's and channel's domains list"
                )
        # purposefully not using humanize_list() here to avoid confusion
        domains_list = ", ".join(channel_data.scoped_domains_list) or "*Empty*"
        await ctx.send(
            f"**LinkWarner's Channel Settings for {channel.mention}**\n\n"
            ">>> "
            f"**Ignored:** {ignored}\n"
            f"**Domains list mode:** {domains_mode}\n"
            f"**Channel's domains list:** {domains_list}"
        )

    # Enabled/ignored state commands
    @linkwarner.command(name="state")
    async def linkwarner_state(self, ctx: GuildContext, new_state: bool) -> None:
        """
        Set if LinkWarner should be enabled for this guild.

        If used without a setting, this will show the current state.
        """
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.set_enabled_state(new_state)

        if new_state:
            message = "Bot will now filter links in this server."
        else:
            message = "Bot will no longer filter links in this server."
        await ctx.send(message)

    @linkwarner_channel.command(name="ignore")
    async def linkwarner_channel_ignore(
        self, ctx: GuildContext, channel: ConfigurableChannel, new_state: bool
    ) -> None:
        """Set if LinkWarner should ignore links in provided channel."""
        channel_data = await self.get_channel_data(channel)
        await channel_data.set_ignored_state(new_state)

        if new_state:
            message = f"Bot will now ignore links in {channel.mention} channel."
        else:
            message = f"Bot will now filter links in {channel.mention} channel."
        await ctx.send(message)

    # Command for Use DMs setting
    @linkwarner.command(name="usedms")
    async def linkwarner_usedms(self, ctx: GuildContext, new_state: bool) -> None:
        """
        Set if LinkWarner should use DMs for warning messages.

        Note: This is NOT recommended as the user might block the bot or all DMs
        from the server and the warning might not get sent to the offender at all.
        This also means that the bot is more likely to get ratelimited for repeatedly
        trying to DM the user when they spam links.

        If you're trying to minimize spam that the warning messages cause,
        you should consider enabling delete delay instead.
        """
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.set_use_dms(new_state)

        if new_state:
            message = "Bot will now send the warning message in DMs."
        else:
            message = (
                "Bot will now send the warning message in the channel"
                " where the link was sent in."
            )
        await ctx.send(message)

    # Delete delay commands
    @linkwarner.group(name="deletedelay", invoke_without_command=True)
    async def linkwarner_deletedelay(self, ctx: GuildContext, new_value: int) -> None:
        """
        Set the delete delay (in seconds) for the warning message.

        Use `[p]linkwarner deletedelay disable` to disable auto-deletion.

        Note: This does not work when the warning messages are sent through DMs.
        """
        if new_value < 1:
            command = inline(f"{ctx.clean_prefix}linkwarner deletedelay disable")
            await ctx.send(
                "The delete delay cannot be lower than 1 second."
                f" If you want to disable auto-deletion, use {command}."
            )
            return
        if new_value > 300:
            await ctx.send(
                "The delete delay cannot be higher than 5 minutes (300 seconds)."
            )
            return

        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.set_delete_delay(new_value)
        plural = "s" if new_value > 1 else ""
        await ctx.send(
            "Bot will now auto-delete the warning message"
            f" after {new_value} second{plural}."
        )

    @linkwarner_deletedelay.command(name="disable")
    async def linkwarner_deletedelay_disable(self, ctx: GuildContext) -> None:
        """Disable auto-deletion of the warning messages."""
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.set_delete_delay(None)
        await ctx.send("Bot will no longer delete the warning messages automatically.")

    # Excluded roles commands
    @linkwarner.group(name="excludedroles")
    async def linkwarner_excludedroles(self, ctx: GuildContext) -> None:
        """Settings for roles that are excluded from getting filtered."""

    @linkwarner_excludedroles.command(name="add", require_var_positional=True)
    async def linkwarner_excludedroles_add(
        self, ctx: GuildContext, *roles: discord.Role
    ) -> None:
        """Add roles that will be excluded from getting filtered."""
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.add_excluded_roles(role.id for role in roles)
        await ctx.send("Excluded roles updated.")

    @linkwarner_excludedroles.command(
        name="remove", aliases=["delete"], require_var_positional=True
    )
    async def linkwarner_excludedroles_remove(
        self, ctx: GuildContext, *roles: discord.Role
    ) -> None:
        """Remove roles that will be excluded from getting filtered."""
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.remove_excluded_roles(role.id for role in roles)
        await ctx.send("Excluded roles updated.")

    # Domains list commands
    @linkwarner.group(name="domains")
    async def linkwarner_domains(self, ctx: GuildContext) -> None:
        """Configuration for allowed/disallowed domains in the guild."""

    @linkwarner_channel.group(name="domains")
    async def linkwarner_channel_domains(self, ctx: GuildContext) -> None:
        """Configuration for allowed/disallowed domains in the specific channel."""

    @linkwarner_domains.command(name="setmode")
    async def linkwarner_domains_setmode(
        self, ctx: GuildContext, new_mode: GuildDomainsMode
    ) -> None:
        """
        Change current domains list mode.

        Available modes:
        `1` - Only domains on the domains list can be sent.
        `2` - All domains can be sent except the ones on the domains list.
        """
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.set_domains_mode(new_mode)

        if new_mode is DomainsMode.ALLOW_FROM_SCOPE_LIST:
            message = "Bot will now only allow domains from the domains list."
        else:
            message = "Bot will now only allow domains that aren't on the domains list."
        await ctx.send(message)

    @linkwarner_channel_domains.command(name="setmode")
    async def linkwarner_channel_domains_setmode(
        self,
        ctx: GuildContext,
        channel: ConfigurableChannel,
        new_mode: DomainsMode,
    ) -> None:
        """
        Change current domains list mode.

        Available modes:
        `0` - Inherit the guild setting and use domains
              from both guild's and channel's domain list.
        `1` - Only domains on the channel's domains list can be sent.
        `2` - All domains can be sent except the ones on the channel's domains list.
        """
        channel_data = await self.get_channel_data(channel)
        guild_data = channel_data.guild_data
        await channel_data.set_domains_mode(new_mode)

        if new_mode is DomainsMode.ALLOW_FROM_SCOPE_LIST:
            message = (
                f"For {channel.mention}, bot will now only allow domains"
                " from the channel's domains list."
            )
        elif new_mode is DomainsMode.DISALLOW_FROM_SCOPE_LIST:
            message = (
                f"For {channel.mention}, bot will now only allow domains"
                " that aren't on the channel's domains list."
            )
        else:
            if guild_data.domains_mode is DomainsMode.ALLOW_FROM_SCOPE_LIST:
                message = (
                    f"For {channel.mention}, bot will now only allow domains"
                    " from the guild's and channel's domains list."
                )
            else:
                message = (
                    f"For {channel.mention}, bot will now only allow domains"
                    " that aren't on the guild's nor channel's domains list."
                )
        await ctx.send(message)

    @linkwarner_domains.command(name="add", require_var_positional=True)
    async def linkwarner_domains_add(
        self, ctx: GuildContext, *domains: DomainName
    ) -> None:
        """
        Add domains to the domains list.

        Note: The cog is using exact matching for domain names
        which means that domain names like youtube.com and www.youtube.com
        are treated as 2 different domains.

        Example:
        `[p]linkwarner domains add google.com youtube.com`
        """
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.add_domains(domains)
        await ctx.send("Domains list updated.")

    @linkwarner_channel_domains.command(name="add", require_var_positional=True)
    async def linkwarner_channel_domains_add(
        self, ctx: GuildContext, channel: ConfigurableChannel, *domains: DomainName
    ) -> None:
        """
        Add domains to the domains list of the provided channel.

        Note: The cog is using exact matching for domain names
        which means that domain names like youtube.com and www.youtube.com
        are treated as 2 different domains.

        Example:
        `[p]linkwarner channel domains add #channel youtube.com discord.com`
        """
        channel_data = await self.get_channel_data(channel)
        await channel_data.add_domains(domains)
        await ctx.send("Domains list updated.")

    @linkwarner_domains.command(
        name="remove", aliases=["delete"], require_var_positional=True
    )
    async def linkwarner_domains_remove(
        self, ctx: GuildContext, *domains: DomainName
    ) -> None:
        """
        Remove domains from the domains list.

        Example:
        `[p]linkwarner domains remove youtube.com discord.com`
        """
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.remove_domains(domains)
        await ctx.send("Domains list updated.")

    @linkwarner_channel_domains.command(
        name="remove", aliases=["delete"], require_var_positional=True
    )
    async def linkwarner_channel_domains_remove(
        self, ctx: GuildContext, channel: ConfigurableChannel, *domains: DomainName
    ) -> None:
        """
        Remove domains from the domains list of the provided channel.

        Example:
        `[p]linkwarner channel domains remove #channel youtube.com discord.com`
        """
        channel_data = await self.get_channel_data(channel)
        await channel_data.remove_domains(domains)
        await ctx.send("Domains list updated.")

    @linkwarner_domains.command(name="clear")
    async def linkwarner_domains_clear(self, ctx: GuildContext) -> None:
        """Clear domains from the domains list."""
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.clear_domains()
        await ctx.send("Domains list cleared.")

    @linkwarner_channel_domains.command(name="clear")
    async def linkwarner_channel_domains_clear(
        self, ctx: GuildContext, channel: ConfigurableChannel
    ) -> None:
        """Clear domains from the domains list of the provided channel."""
        channel_data = await self.get_channel_data(channel)
        await channel_data.clear_domains()
        await ctx.send("Domains list cleared.")

    # Warning message commands
    @linkwarner.command(name="setmessage")
    async def linkwarner_setmessage(self, ctx: GuildContext, *, message: str) -> None:
        """
        Set link warning message.

        Those fields will get replaced automatically:
        $mention - Mention the user who sent the message with a link
        $username - The user's display name
        $server - The name of the server
        """
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.set_warn_message(message)

        content = guild_data.format_warn_message(ctx.message)
        # we've just set the template, content can't be None
        assert content is not None, "mypy"
        await ctx.send("Link warning message set, sending a test message here...")
        await ctx.send(content)

    @linkwarner_channel.command(name="setmessage")
    async def linkwarner_channel_setmessage(
        self, ctx: GuildContext, channel: ConfigurableChannel, *, message: str
    ) -> None:
        """
        Set link warning message for provided channel.

        Those fields will get replaced automatically:
        $mention - Mention the user who sent the message with a link
        $username - The user's display name
        $server - The name of the server
        """
        channel_data = await self.get_channel_data(channel)
        await channel_data.set_warn_message(message)

        content = channel_data.format_warn_message(ctx.message)
        # we've just set the template, content can't be None
        assert content is not None, "mypy"
        await ctx.send("Link warning message set, sending a test message here...")
        await ctx.send(content)

    @linkwarner.command(name="unsetmessage")
    async def linkwarner_unsetmessage(self, ctx: GuildContext) -> None:
        """Unset link warning message."""
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.set_warn_message("")
        await ctx.send("Link warning message unset.")

    @linkwarner_channel.command(name="unsetmessage")
    async def linkwarner_channel_unsetmessage(
        self, ctx: GuildContext, channel: ConfigurableChannel
    ) -> None:
        """Unset link warning message for provided channel."""
        channel_data = await self.get_channel_data(channel)
        await channel_data.set_warn_message("")
        await ctx.send("Link warning message unset.")

    async def _should_ignore(
        self, message: discord.Message, *, edit: bool = False
    ) -> bool:
        """
        Checks whether message should be ignored in the `on_message` listener.

        This checks whether:
        - message has been sent in guild
        - message author is a bot
        - cog is disabled in guild
        - message author is on Red's immunity list for automated moderator actions
        - channel is ignored in cog's settings
        - message author has any role that is excluded from the filter in cog's settings

        Returns
        -------
        bool
            `True` if message should be ignored, `False` otherwise
        """
        guild = message.guild
        if guild is None or message.author.bot:
            return True

        if isinstance(message.channel, discord.PartialMessageable):
            return True

        if await self.bot.cog_disabled_in_guild(self, guild):
            return True

        if await self.bot.is_automod_immune(message):
            return True

        assert not isinstance(
            message.channel, (discord.DMChannel, discord.GroupChannel)
        ), "mypy"
        assert isinstance(message.author, discord.Member), "mypy"
        try:
            channel_data = await self.get_channel_data(message.channel)
        except RuntimeError:
            return True
        if not channel_data.enabled:
            return True

        if channel_data.guild_data.has_excluded_roles(message.author):
            return True

        if edit and not channel_data.guild_data.check_edits:
            return True

        return False

    # listener
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message, *, edit: bool = False) -> None:
        if await self._should_ignore(message, edit=edit):
            return

        guild = message.guild
        channel = message.channel
        author = message.author
        assert guild is not None, "mypy"
        assert not isinstance(
            channel,
            (discord.DMChannel, discord.GroupChannel, discord.PartialMessageable),
        ), "mypy"

        channel_data = await self.get_channel_data(channel)
        guild_data = channel_data.guild_data

        assert guild.me is not None, "mypy"
        for match in URL_RE.finditer(message.content):
            if channel_data.is_url_allowed(match.group(2)):
                continue

            try:
                if not channel.permissions_for(guild.me).manage_messages:
                    raise RuntimeError
                await message.delete()
            except (discord.Forbidden, RuntimeError):
                log.error(
                    "Bot can't delete messages in channel with ID %s (guild ID: %s)",
                    channel.id,
                    guild.id,
                )
            except discord.NotFound:
                # message had been removed before we got to it
                pass
            msg = channel_data.format_warn_message(message)
            if msg is not None:
                if guild_data.use_dms:
                    try:
                        await author.send(msg)
                    except discord.Forbidden:
                        log.info(
                            "Bot couldn't send a message to the user with ID %s",
                            author.id,
                        )
                else:
                    try:
                        if not can_user_send_messages_in(guild.me, channel):
                            raise RuntimeError
                        if guild_data.delete_delay is not None:
                            await channel.send(
                                msg, delete_after=guild_data.delete_delay
                            )
                        else:
                            await channel.send(msg)
                    except (discord.Forbidden, RuntimeError):
                        log.error(
                            "Bot can't send messages in channel with ID %s"
                            " (guild ID: %s)",
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
                channel=channel,
            )
            return

    @commands.Cog.listener()
    async def on_message_edit(
        self, _before: discord.Message, after: discord.Message
    ) -> None:
        await self.on_message(after, edit=True)
