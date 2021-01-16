# Copyright 2018-2021 Jakub Kuczys (https://github.com/jack1142)
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

import re
from string import Template
from typing import Dict, Iterable, Optional, Pattern, Set


class GuildData:
    """Cached guild data.

    Attributes
    ----------
    id: `int`
        Guild ID.
    enabled: `bool`
        Is LinkWarner enabled for this guild.
    exclude_roles: `set` of `int`
        Role IDs that should be excluded from filtering in this guild
    exclude_domains: `set` of `str`
        Domains that are excluded from filtering in this guild.
    domains_filter: `Pattern[str]`
        Compiled regex to check if domain is excluded from filtering.
    warn_message: `str`
        Warn message for this guild.
    warn_message_template: `Template`, optional
        Warning message template if message is set, otherwise `None`.

    """

    __slots__ = (
        "id",
        "enabled",
        "exclude_roles",
        "exclude_domains",
        "domains_filter",
        "warn_message",
        "warn_message_template",
        "channel_cache",
    )

    def __init__(
        self,
        guild_id: int,
        *,
        enabled: bool,
        exclude_roles: Iterable[int],
        exclude_domains: Iterable[str],
        warn_message: str,
    ) -> None:
        # TODO: put channel cache in guild data object
        self.id: int = guild_id
        self.enabled: bool
        self.exclude_roles: Set[int]
        self.exclude_domains: Set[str]
        self.domains_filter: Optional[Pattern[str]]
        self.warn_message: str
        self.warn_message_template: Optional[Template]
        self.channel_cache: Dict[int, ChannelData] = {}

        self.update_enabled_state(enabled)
        self.update_excluded_roles(exclude_roles)
        self.update_excluded_domains(exclude_domains)
        self.update_warn_message(warn_message)

    def update_enabled_state(self, enabled: bool) -> None:
        self.enabled = enabled

        # update channel cache with new enabled state
        for channel_data in self.channel_cache.values():
            channel_data.update_ignore_state()

    def update_excluded_roles(self, exclude_roles: Iterable[int]) -> None:
        self.exclude_roles = set(exclude_roles)

    def add_excluded_roles(self, to_add: Iterable[int]) -> None:
        self.exclude_roles.update(to_add)

    def remove_excluded_roles(self, to_remove: Iterable[int]) -> None:
        self.exclude_roles.difference_update(to_remove)

    def update_excluded_domains(
        self, exclude_domains: Optional[Iterable[str]] = None
    ) -> None:
        if exclude_domains is not None:
            self.exclude_domains = set(exclude_domains)

        if self.exclude_domains:
            self.domains_filter = re.compile(
                f"^({'|'.join(re.escape(domain) for domain in self.exclude_domains)})",
                flags=re.I,
            )
        else:
            self.domains_filter = None

        # update channel cache with new excluded domains set
        for channel_data in self.channel_cache.values():
            channel_data.update_excluded_domains()

    def add_excluded_domains(self, to_add: Iterable[str]) -> None:
        self.exclude_domains.update(to_add)
        self.update_excluded_domains()

    def remove_excluded_domains(self, to_remove: Iterable[str]) -> None:
        self.exclude_domains.difference_update(to_remove)
        self.update_excluded_domains()

    def update_warn_message(self, warn_message: str) -> None:
        self.warn_message = warn_message
        if warn_message:
            self.warn_message_template = Template(warn_message)
        else:
            self.warn_message_template = None

        # update channel cache with new warn message
        for channel_data in self.channel_cache.values():
            channel_data.update_warn_message()


class ChannelData:
    """Cached channel data.

    Attributes
    ----------
    id: `int`
        Channel ID.
    ignore: `bool`
        Is channel ignored when checking for links.
    channel_exclude_domains: `set` of `str`
        Domains excluded from filtering specifically in this channel.
    warn_message: `str`
        Warn message specifically in this channel.
    guild_data: `GuildData`
        Guild data for the guild the channel is in.
    enabled: `bool`
        Is channel checked for links (includes guild settings).
    exclude_domains: `set` of `str`
        Domains that are excluded from filtering
        in this channel (includes guild settings).
    domains_filter: `Pattern[str]`
        Compiled regex to check if domain is excluded
        from filtering (includes guild settings).
    warn_message_template: `Template`, optional
        Warning message template if warn message is set
        in guild or channel, otherwise `None`.

    """

    __slots__ = (
        "id",
        "ignore",
        "channel_exclude_domains",
        "warn_message",
        "guild_data",
        "enabled",
        "exclude_domains",
        "domains_filter",
        "warn_message_template",
    )

    def __init__(
        self,
        channel_id: int,
        *,
        ignore: bool,
        exclude_domains: Iterable[str],
        warn_message: str,
        guild_data: GuildData,
    ) -> None:
        # Channel settings without guild-inherited settings
        self.id: int = channel_id
        self.ignore: bool = ignore
        self.channel_exclude_domains: Set[str] = set(exclude_domains)
        self.warn_message: str = warn_message
        # Settings that apply to channel with guild-inherited settings
        self.guild_data: GuildData
        self.enabled: bool
        self.exclude_domains: Set[str]
        self.domains_filter: Optional[Pattern[str]]
        self.warn_message_template: Optional[Template]

        self.update_guild_data(guild_data)

    def update_guild_data(self, guild_data: Optional[GuildData] = None) -> None:
        if guild_data is not None:
            self.guild_data = guild_data
        self.update_ignore_state()
        self.update_excluded_domains()
        self.update_warn_message()

    def update_ignore_state(self, ignore: Optional[bool] = None) -> None:
        if ignore is not None:
            self.ignore = ignore

        self.enabled = self.guild_data.enabled and not self.ignore

    def update_excluded_domains(
        self, exclude_domains: Optional[Iterable[str]] = None
    ) -> None:
        guild_data = self.guild_data
        if exclude_domains is not None:
            self.channel_exclude_domains = set(exclude_domains)

        if self.channel_exclude_domains:
            self.exclude_domains = (
                guild_data.exclude_domains | self.channel_exclude_domains
            )
            self.domains_filter = re.compile(
                f"^({'|'.join(re.escape(domain) for domain in self.exclude_domains)})",
                flags=re.I,
            )
        else:
            self.exclude_domains = guild_data.exclude_domains
            self.domains_filter = guild_data.domains_filter

    def add_excluded_domains(self, to_add: Iterable[str]) -> None:
        self.channel_exclude_domains.update(to_add)
        self.update_excluded_domains()

    def remove_excluded_domains(self, to_remove: Iterable[str]) -> None:
        self.channel_exclude_domains.difference_update(to_remove)
        self.update_excluded_domains()

    def update_warn_message(self, warn_message: Optional[str] = None) -> None:
        if warn_message is not None:
            self.warn_message = warn_message

        if warn_message:
            self.warn_message_template = Template(self.warn_message)
        else:
            self.warn_message_template = self.guild_data.warn_message_template
