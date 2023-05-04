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

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from enum import Enum
from string import Template
from typing import TYPE_CHECKING, Dict, Iterable, Optional, Pattern, Set, Union

import discord
from redbot.core import commands
from redbot.core.config import Config, Group
from redbot.core.utils.chat_formatting import inline

ConfigurableChannel = Union[
    discord.TextChannel,
    discord.VoiceChannel,
    discord.StageChannel,
    discord.ForumChannel,
]


class DomainsMode(Enum):
    #: Inherit the guild setting and use domains
    #: from both guild's and channel's domain list.
    INHERIT_MODE_AND_UNION_LISTS = 0
    #: Only domains on the channel's domains list can be sent.
    ALLOW_FROM_SCOPE_LIST = 1
    #: All domains can be sent except the ones on the channel's domains list.
    DISALLOW_FROM_SCOPE_LIST = 2

    @classmethod
    async def convert(cls, _ctx: commands.Context, arg: str) -> DomainsMode:
        try:
            return DomainsMode(int(arg))
        except ValueError:
            raise commands.BadArgument(
                f"{inline(arg)} is not a valid domains list mode."
            )


if TYPE_CHECKING:
    GuildDomainsMode = DomainsMode
else:

    class GuildDomainsMode:
        @classmethod
        async def convert(cls, _ctx: commands.Context, arg: str) -> DomainsMode:
            try:
                ret = DomainsMode(int(arg))
                if ret is DomainsMode.INHERIT_MODE_AND_UNION_LISTS:
                    raise ValueError("Mode can't be inherited in guild scope.")
            except ValueError:
                raise commands.BadArgument(
                    f"{inline(arg)} is not a valid domains list mode."
                )
            return ret


class ScopeData(ABC):
    """
    Abstract class for scope data.

    Attributes
    ----------
    id: `int`
        Discord ID of the scope.
    config_group: `Group`
        Config group for the given instance of ScopeData subclass.
    domains_mode: `DomainsMode`
        Mode of the domains list.
    scoped_domains_list: `set` of `str`
        Scope's domains list.
    scoped_warn_message: `str`
        Warn message specifically in this scope.
    domains_list: `set` of `str`
        Domains list of this scope and the scopes it inherits from (if any).
    domains_filter: `Pattern[str]`
        Compiled regex matching domains from the `domains_list`.
    warn_message_template: `Template`, optional
        Warning message template if warn message is set
        in this scope or any above, otherwise `None`.
    """

    __slots__ = (
        "id",
        "domains_mode",
        "scoped_domains_list",
        "scoped_warn_message",
        "domains_filter",
        "warn_message_template",
    )
    id: int
    domains_mode: DomainsMode
    scoped_domains_list: Set[str]
    scoped_warn_message: str
    domains_filter: Optional[Pattern[str]]
    warn_message_template: Optional[Template]

    @property
    @abstractmethod
    def config_group(self) -> Group:
        raise NotImplementedError

    @property
    @abstractmethod
    def domains_list(self) -> Set[str]:
        raise NotImplementedError

    async def set_domains_mode(self, new_mode: DomainsMode) -> None:
        self.domains_mode = new_mode
        self._update_domains_list()
        await self.config_group.domains_mode.set(new_mode.value)

    async def add_domains(self, to_add: Iterable[str]) -> None:
        self.scoped_domains_list.update(to_add)
        self._update_domains_list()
        await self.config_group.domains_list.set(list(self.scoped_domains_list))

    async def remove_domains(self, to_remove: Iterable[str]) -> None:
        self.scoped_domains_list.difference_update(to_remove)
        self._update_domains_list()
        await self.config_group.domains_list.set(list(self.scoped_domains_list))

    async def clear_domains(self) -> None:
        self.scoped_domains_list.clear()
        self._update_domains_list()
        await self.config_group.domains_list.set(list(self.scoped_domains_list))

    async def set_warn_message(self, warn_message: str) -> None:
        self.scoped_warn_message = warn_message
        self._update_warn_message()
        await self.config_group.warn_message.set(warn_message)

    def format_warn_message(self, message: discord.Message) -> Optional[str]:
        if self.warn_message_template is None:
            return None
        assert isinstance(message.guild, discord.Guild), "mypy"
        return self.warn_message_template.safe_substitute(
            mention=message.author.mention,
            username=str(message.author),
            server=message.guild.name,
        )

    @abstractmethod
    def _update_domains_list(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def _update_warn_message(self) -> None:
        raise NotImplementedError


class GuildData(ScopeData):
    """
    Cached guild data.

    Attributes
    ----------
    id: `int`
        Guild ID.
    enabled: `bool`
        Is LinkWarner enabled for this guild.
    check_edits: `bool`
        Whether LinkWarner should check the messages for links on edit.
    use_dms: `bool`
        Whether LinkWarner should send the warning messages in DMs.
    delete_delay: `Optional[int]`
        The amount of seconds to wait before auto-deleting warning messages.
        `None` if the warning messages should not be auto-deleted.
    excluded_roles: `set` of `int`
        Role IDs that should be excluded from filtering in this guild.
    domains_mode: `DomainsMode`
        Mode of the domains list.
        This should never be `DomainsMode.INHERIT_MODE_AND_UNION_LISTS`.
    domains_list: `set` of `str`
        Guild's domains list.
    domains_filter: `Pattern[str]`
        Compiled regex matching domains from the `domains_list`.
    scoped_warn_message: `str`
        Warn message for this guild.
    warn_message_template: `Template`, optional
        Warning message template if message is set, otherwise `None`.
    """

    __slots__ = (
        "_config",
        "_config_group",
        "enabled",
        "check_edits",
        "use_dms",
        "delete_delay",
        "excluded_roles",
        "_channel_cache",
    )

    def __init__(
        self,
        config: Config,
        guild_id: int,
        *,
        enabled: bool,
        check_edits: bool,
        use_dms: bool,
        delete_delay: Optional[int],
        excluded_roles: Iterable[int],
        domains_mode: int,
        domains_list: Iterable[str],
        warn_message: str,
    ) -> None:
        self.id = guild_id
        self._config: Config = config
        self._channel_cache: Dict[int, ChannelData] = {}

        self._config_group: Group

        self.enabled = enabled
        self.check_edits = check_edits
        self.use_dms = use_dms
        self.delete_delay = delete_delay
        self.excluded_roles = set(excluded_roles)
        self.domains_mode = DomainsMode(domains_mode)
        self.scoped_domains_list = set(domains_list)
        self.scoped_warn_message = warn_message

        self._update_domains_list()
        self._update_warn_message()

    @property
    def config_group(self) -> Group:
        try:
            return self._config_group
        except AttributeError:
            config_group = self._config.guild_from_id(self.id)
            self._config_group = config_group
            return config_group

    @property
    def domains_list(self) -> Set[str]:
        return self.scoped_domains_list

    @classmethod
    async def from_guild(cls, config: Config, guild: discord.Guild) -> GuildData:
        data = await config.guild(guild).all()
        return cls(config, guild.id, **data)

    async def get_channel_data(self, channel: ConfigurableChannel) -> ChannelData:
        try:
            return self._channel_cache[channel.id]
        except KeyError:
            pass

        data = await ChannelData.from_channel(self, channel)
        self._channel_cache[channel.id] = data

        return data

    async def set_enabled_state(self, new_state: bool) -> None:
        self.enabled = new_state
        await self.config_group.enabled.set(new_state)

        # update channel cache with new enabled state
        for channel_data in self._channel_cache.values():
            channel_data._update_enabled()

    async def set_domains_mode(self, new_mode: DomainsMode) -> None:
        if new_mode is DomainsMode.INHERIT_MODE_AND_UNION_LISTS:
            raise ValueError("Mode can't be inherited in the guild scope.")
        await super().set_domains_mode(new_mode)

    def has_excluded_roles(self, member: discord.Member) -> bool:
        """
        Check if the given member has at least one of the roles
        from the excluded roles list.
        """
        common_roles = self.excluded_roles.intersection(
            role.id for role in member.roles
        )
        return bool(common_roles)

    async def set_check_edits(self, new_state: bool) -> None:
        self.check_edits = new_state
        await self.config_group.check_edits.set(new_state)

    async def set_use_dms(self, new_state: bool) -> None:
        self.use_dms = new_state
        await self.config_group.use_dms.set(new_state)

    async def set_delete_delay(self, new_value: Optional[int]) -> None:
        self.delete_delay = new_value
        await self.config_group.delete_delay.set(new_value)

    async def set_excluded_roles(self, excluded_roles: Iterable[int]) -> None:
        self.excluded_roles = set(excluded_roles)
        await self.config_group.excluded_roles.set(list(self.excluded_roles))

    async def add_excluded_roles(self, to_add: Iterable[int]) -> None:
        self.excluded_roles.update(to_add)
        await self.config_group.excluded_roles.set(list(self.excluded_roles))

    async def remove_excluded_roles(self, to_remove: Iterable[int]) -> None:
        self.excluded_roles.difference_update(to_remove)
        await self.config_group.excluded_roles.set(list(self.excluded_roles))

    def _update_domains_list(self) -> None:
        if self.domains_list:
            joined_domains = "|".join(
                rf"{re.escape(domain)}(?:$|/)" for domain in self.domains_list
            )
            self.domains_filter = re.compile(f"^({joined_domains})", flags=re.I)
        else:
            self.domains_filter = None

        # update channel cache with new excluded domains set
        for channel_data in self._channel_cache.values():
            channel_data._update_domains_list()

    def _update_warn_message(self) -> None:
        if self.scoped_warn_message:
            self.warn_message_template = Template(self.scoped_warn_message)
        else:
            self.warn_message_template = None

        # update channel cache with new warn message
        for channel_data in self._channel_cache.values():
            channel_data._update_warn_message()


class ChannelData(ScopeData):
    """
    Cached channel data.

    Attributes
    ----------
    id: `int`
        Channel ID.
    guild_data: `GuildData`
        Guild data for the guild the channel is in.
    ignored: `bool`
        Is channel ignored when checking for links.
    enabled: `bool`
        Should channel be checked for links (includes guild's ``enabled`` setting).
    domains_mode: `DomainsMode`
        Mode of the domains list.
    scoped_domains_list: `set` of `str`
        Channel's domain list
    domains_list: `set` of `str`
        Domains list containing domains from `scoped_domains_list` and additionally,
        if domains mode is set to inherit, also domains from the guild's domain list.
    domains_filter: `Pattern[str]`
        Compiled regex matching domains from the `domains_list`.
    scoped_warn_message: `str`
        Warn message specifically in this channel.
    warn_message_template: `Template`, optional
        Warning message template if warn message is set
        in guild or channel, otherwise `None`.
    """

    __slots__ = (
        "guild_data",
        "_config_group",
        "ignored",
        "enabled",
        "_domains_list",
    )

    def __init__(
        self,
        guild_data: GuildData,
        channel_id: int,
        *,
        ignored: bool,
        domains_mode: int,
        domains_list: Iterable[str],
        warn_message: str,
    ) -> None:
        self.id: int = channel_id
        self.guild_data = guild_data
        self._config_group: Group

        # Channel settings without guild-inherited settings
        self.ignored: bool = ignored
        self.domains_mode = DomainsMode(domains_mode)
        self.scoped_domains_list: Set[str] = set(domains_list)
        self.scoped_warn_message: str = warn_message

        # Settings that apply to channel with guild-inherited settings
        self.enabled: bool
        self._domains_list: Set[str]

        self._update_enabled()
        self._update_domains_list()
        self._update_warn_message()

    @property
    def config_group(self) -> Group:
        try:
            return self._config_group
        except AttributeError:
            config_group = self.guild_data._config.channel_from_id(self.id)
            self._config_group = config_group
            return config_group

    @property
    def domains_list(self) -> Set[str]:
        return self._domains_list

    @domains_list.setter
    def domains_list(self, value: Set[str]) -> None:
        self._domains_list = value

    @classmethod
    async def from_channel(
        cls, guild_data: GuildData, channel: ConfigurableChannel
    ) -> ChannelData:
        data = await guild_data._config.channel(channel).all()
        return cls(guild_data, channel.id, **data)

    async def set_ignored_state(self, new_state: bool) -> None:
        self.ignored = new_state
        self._update_enabled()
        await self.config_group.ignored.set(new_state)

    def is_url_allowed(self, url: str) -> bool:
        """
        Check if the URL should be allowed using current domains mode and domains list.
        """
        domains_mode = self.domains_mode
        if domains_mode is DomainsMode.INHERIT_MODE_AND_UNION_LISTS:
            domains_mode = self.guild_data.domains_mode

        if self.domains_filter is None:
            return domains_mode is DomainsMode.DISALLOW_FROM_SCOPE_LIST

        return (domains_mode is DomainsMode.ALLOW_FROM_SCOPE_LIST) ^ (
            self.domains_filter.match(url) is None
        )

    def _update_enabled(self) -> None:
        self.enabled = self.guild_data.enabled and not self.ignored

    def _update_domains_list(self) -> None:
        self.domains_list = set(self.scoped_domains_list)
        self.domains_filter = None
        if self.domains_mode is DomainsMode.INHERIT_MODE_AND_UNION_LISTS:
            self.domains_list |= self.guild_data.domains_list
            self.domains_filter = self.guild_data.domains_filter

        if self.scoped_domains_list:
            joined_domains = "|".join(
                rf"{re.escape(domain)}(?:$|/)" for domain in self.domains_list
            )
            self.domains_filter = re.compile(
                f"^({joined_domains})",
                flags=re.I,
            )

    def _update_warn_message(self) -> None:
        if self.scoped_warn_message:
            self.warn_message_template = Template(self.scoped_warn_message)
        else:
            self.warn_message_template = self.guild_data.warn_message_template
