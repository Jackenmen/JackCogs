"""
Copyright 2018-2020 Jakub Kuczys (https://github.com/jack1142)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

import discord
from redbot.core.config import Config, Group


class GuildData:
    __slots__ = (
        "id",
        "_config",
        "_config_group",
        "blocklist_mode",
        "file_extensions",
        "_channel_cache",
    )

    def __init__(
        self,
        config: Config,
        guild_id: int,
        *,
        blocklist_mode: bool,
        file_extensions: Sequence[str],
    ) -> None:
        self.id: int = guild_id
        self._config: Config = config
        self._config_group: Group
        self.blocklist_mode: bool = blocklist_mode
        self.file_extensions: Tuple[str, ...] = tuple(file_extensions)
        # state tri-bool
        self._channel_cache: Dict[int, Optional[bool]] = {}

    @property
    def config_group(self) -> Group:
        try:
            return self._config_group
        except AttributeError:
            config_group = self._config.guild_from_id(self.id)
            self._config_group = config_group
            return config_group

    @classmethod
    async def from_guild(cls, config: Config, guild: discord.Guild) -> GuildData:
        data = await config.guild(guild).all()
        return cls(config, guild.id, **data)

    async def get_channel_state(self, channel: discord.TextChannel) -> Optional[bool]:
        try:
            return self._channel_cache[channel.id]
        except KeyError:
            pass

        state = await self._config.channel(channel).state()
        self._channel_cache[channel.id] = state

        return state

    async def is_enabled_for_channel(self, channel: discord.TextChannel) -> bool:
        channel_state = await self.get_channel_state(channel)
        if self.blocklist_mode:
            if channel_state is False:
                return False
        else:
            if channel_state is not True:
                return False

        return True
