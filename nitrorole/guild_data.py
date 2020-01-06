from string import Template
from typing import List, Optional

import discord
from redbot.core.config import Config


class cached_property:
    def __init__(self, func):
        self.func = func

    def __get__(self, instance, owner):
        if instance is None:
            return self

        value = self.func(instance)
        setattr(instance, self.func.__name__, value)

        return value


class GuildData:
    """
    Cached guild data.

    Attributes
    ----------
    id: `int`
        Guild ID.
    role_id: `int`, optional
        ID of a role to assign to a new nitro booster,
        `None` if no role should be assigned.
    channel_id: `int`, optional
        ID of a channel where new nitro booster messages should be sent,
        `None` if no channel is set.
    messages: `list` of `str`
        List of new nitro booster messages for this guild.
    message_templates: `list` of `Template`
        List of new nitro booster message templates for this guild.
    unassign_on_boost_end: bool
        Should the role with `role_id` be removed when user stops boosting server.

    """

    __slots__ = (
        "id",
        "_config",
        "role_id",
        "channel_id",
        "messages",
        "message_templates",
        "unassign_on_boost_end",
    )

    def __init__(
        self,
        guild_id: int,
        config: Config,
        *,
        role_id: Optional[int],
        channel_id: Optional[int],
        message_templates: List[str],
        unassign_on_boost_end: bool,
    ) -> None:
        self.id: int = guild_id
        self._config: Config = config
        self.role_id: Optional[int] = role_id
        self.channel_id: Optional[int] = channel_id
        self.messages: List[str]
        self.message_templates: List[Template]
        self.unassign_on_boost_end: bool = unassign_on_boost_end

        self._update_messages(message_templates)

    @cached_property
    def config_scope(self):
        return self._config.guild(discord.Object(id=self.id))

    async def set_unassign_on_boost_end(self, state: bool) -> None:
        self.unassign_on_boost_end = state
        await self.config_scope.unassign_on_boost_end.set(state)

    async def set_role(self, role: Optional[discord.Role]) -> None:
        if role is None:
            self.role_id = None
            await self.config_scope.role_id.clear()
        else:
            self.role_id = role.id
            await self.config_scope.role_id.set(role.id)

    async def set_channel(self, channel: Optional[discord.TextChannel]) -> None:
        if channel is None:
            self.channel_id = None
            await self.config_scope.channel_id.clear()
        else:
            self.channel_id = channel.id
            await self.config_scope.channel_id.set(channel.id)

    async def add_message(self, message: str) -> Template:
        template = Template(message)
        self.messages.append(message)
        self.message_templates.append(template)
        await self.config_scope.message_templates.set(self.messages)
        return template

    async def remove_message(self, index: int) -> None:
        self.messages.pop(index)
        self.message_templates.pop(index)
        await self.config_scope.message_templates.set(self.messages)

    def _update_messages(self, messages: List[str]) -> None:
        self.messages = messages
        self.message_templates = [Template(message) for message in messages]
