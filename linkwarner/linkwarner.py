import logging
import re
from string import Template
from typing import List, Optional

import discord
from redbot.core import commands, modlog
from redbot.core.bot import Red
from redbot.core.config import Config
from redbot.core.utils.common_filters import URL_RE


log = logging.getLogger("red.jackcogs.linkwarner")


class GuildData:
    def __init__(
        self,
        *,
        enabled: bool,
        exclude_roles: List[int],
        exclude_domains: List[str],
        warn_message: str,
    ):
        self.enabled = enabled
        self.exclude_roles = set(exclude_roles)
        self.exclude_domains = set(exclude_domains)
        self.domains_filter = None
        if self.exclude_domains:
            self.domains_filter = re.compile(
                f"^({'|'.join(re.escape(domain) for domain in self.exclude_domains)})",
                flags=re.I,
            )
        self.warn_message = Template(warn_message)


class ChannelData:
    def __init__(
        self,
        *,
        ignore: bool,
        exclude_domains: List[str],
        warn_message: str,
        guild_data: GuildData,
    ):
        self.enabled = guild_data.enabled and not ignore
        self.guild_data = guild_data
        if exclude_domains:
            self.exclude_domains = guild_data.exclude_domains | set(exclude_domains)
            self.domains_filter = re.compile(
                f"^({'|'.join(re.escape(domain) for domain in self.exclude_domains)})",
                flags=re.I,
            )
        else:
            self.exclude_domains = guild_data.exclude_domains
            self.domains_filter = guild_data.domains_filter
        if warn_message:
            self.warn_message = Template(warn_message)
        else:
            self.warn_message = guild_data.warn_message


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
        self.guild_cache = {}
        self.channel_cache = {}

    async def initialize(self):
        try:
            await modlog.register_casetype(
                name="linkwarn",
                default_setting=True,
                image="\N{WARNING SIGN}",
                case_str="Link Warning",
            )
        except RuntimeError:
            pass

    async def get_guild_data(
        self, guild: discord.Guild, force_refresh: bool = False
    ) -> GuildData:
        if not force_refresh:
            try:
                return self.guild_cache[guild.id]
            except KeyError:
                pass

        guild_settings = await self.config.guild(guild).all()
        data = self.guild_cache[guild.id] = GuildData(**guild_settings)
        return data

    async def get_channel_data(
        self, channel: discord.TextChannel, force_refresh: bool = False
    ) -> ChannelData:
        if not force_refresh:
            try:
                return self.channel_cache[channel.id]
            except KeyError:
                pass

        channel_settings = await self.config.channel(channel).all()
        guild_data = await self.get_guild_data(
            channel.guild, force_refresh=force_refresh
        )

        data = self.channel_cache[channel.id] = ChannelData(
            **channel_settings, guild_data=guild_data
        )
        return data

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        author = message.author
        channel = message.channel
        guild = message.guild
        if guild is None or author.bot:
            return
        if await self.bot.is_automod_immune(message):
            return

        channel_data = await self.get_channel_data(channel)
        guild_data = channel_data.guild_data
        if not channel_data.enabled:
            return

        common_roles = guild_data.exclude_roles.intersection(
            role.id for role in message.author.roles
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
            warn_message = channel_data.warn_message
            if not warn_message:
                return

            try:
                await channel.send(warn_message.safe_substitute(mention=author.mention))
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
