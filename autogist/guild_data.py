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

import contextlib
from typing import Dict, Iterable, Optional, Sequence, Tuple

import discord
from redbot.core.bot import Red
from redbot.core.config import Config, Group

from .discord_utils import GuildMessageable


class GuildData:
    __slots__ = (
        "id",
        "bot",
        "_config",
        "_config_group",
        "blocklist_mode",
        "file_extensions",
        "listen_to_humans",
        "listen_to_bots",
        "listen_to_self",
        "_channel_cache",
    )

    def __init__(
        self,
        bot: Red,
        config: Config,
        guild_id: int,
        *,
        blocklist_mode: bool,
        file_extensions: Sequence[str],
        listen_to_humans: bool,
        listen_to_bots: bool,
        listen_to_self: bool,
    ) -> None:
        self.id: int = guild_id
        self.bot = bot
        self._config: Config = config
        self._config_group: Group
        self.blocklist_mode: bool = blocklist_mode
        self.file_extensions: Tuple[str, ...] = tuple(file_extensions)
        self.listen_to_humans: bool = listen_to_humans
        self.listen_to_bots: bool = listen_to_bots
        self.listen_to_self: bool = listen_to_self
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
    async def from_guild(
        cls, bot: Red, config: Config, guild: discord.Guild
    ) -> GuildData:
        data = await config.guild(guild).all()
        return cls(bot, config, guild.id, **data)

    async def get_channel_state(self, channel: GuildMessageable) -> Optional[bool]:
        try:
            return self._channel_cache[channel.id]
        except KeyError:
            pass

        state: Optional[bool] = await self._config.channel(channel).state()
        self._channel_cache[channel.id] = state

        return state

    async def is_enabled_for_channel(self, channel: GuildMessageable) -> bool:
        channel_state = await self.get_channel_state(channel)
        if self.blocklist_mode:
            if channel_state is False:
                return False
        else:
            if channel_state is not True:
                return False

        return True

    async def is_overridden(self, channel: GuildMessageable) -> bool:
        channel_state = await self.get_channel_state(channel)
        if channel_state is True:
            return not self.blocklist_mode
        if channel_state is False:
            return self.blocklist_mode
        return False

    def is_permitted(self, user: discord.abc.User) -> bool:
        is_self = self.bot.user is not None and user.id == self.bot.user.id
        return (
            (self.listen_to_humans and not user.bot)
            or (self.listen_to_bots and user.bot and not is_self)
            or (self.listen_to_self and is_self)
        )

    async def edit_blocklist_mode(self, state: bool) -> None:
        self.blocklist_mode = state
        await self.config_group.blocklist_mode.set(state)

    async def edit_listen_to_humans(self, state: bool) -> None:
        self.listen_to_humans = state
        await self.config_group.listen_to_humans.set(state)

    async def edit_listen_to_bots(self, state: bool) -> None:
        self.listen_to_bots = state
        await self.config_group.listen_to_bots.set(state)

    async def edit_listen_to_self(self, state: bool) -> None:
        self.listen_to_self = state
        await self.config_group.listen_to_self.set(state)

    async def update_channel_states(
        self, channels: Iterable[GuildMessageable], state: bool
    ) -> None:
        for channel in channels:
            self._channel_cache[channel.id] = state
            await self._config.channel(channel).state.set(state)

    async def add_file_extensions(self, extensions: Iterable[str]) -> None:
        async with self.config_group.file_extensions() as file_extensions:
            for ext in extensions:
                # normalize extension
                ext = f".{ext.lstrip('.').lower()}"
                if ext not in file_extensions:
                    file_extensions.append(ext)

        self.file_extensions = tuple(file_extensions)

    async def remove_file_extensions(self, extensions: Iterable[str]) -> None:
        async with self.config_group.file_extensions() as file_extensions:
            for ext in extensions:
                # normalize extension
                ext = f".{ext.lstrip('.').lower()}"
                with contextlib.suppress(ValueError):
                    file_extensions.remove(ext)

            self.file_extensions = tuple(file_extensions)
