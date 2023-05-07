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

import itertools
import re
from typing import TYPE_CHECKING, Iterator, Optional, Union

import discord
from redbot.core import commands
from redbot.core.commands import GuildContext

"""
Converters below are originally from permissions core cog:
https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/permissions/converters.py
"""
MENTION_RE = re.compile(r"^<?(?:(?:@[!&]?)?|#)(\d{15,21})>?$")


def _match_id(arg: str) -> Optional[int]:
    m = MENTION_RE.match(arg)
    if m:
        return int(m.group(1))
    return None


if TYPE_CHECKING:
    MemberOrRole = Union[discord.Member, discord.Role]
else:

    class MemberOrRole:
        @classmethod
        async def convert(
            cls, ctx: GuildContext, argument: str
        ) -> Union[discord.Member, discord.Role]:
            guild: discord.Guild = ctx.guild
            _id = _match_id(argument)

            if _id is not None:
                member: Optional[discord.Member] = guild.get_member(_id)
                if member is not None:
                    return member

                role: Optional[discord.Role] = guild.get_role(_id)
                if role is not None and not role.is_default():
                    return role

            f = filter(lambda r: not r.is_default(), guild.roles)
            # wrong inferred type: https://github.com/python/mypy/issues/8226
            objects: Iterator[Union[discord.Member, discord.Role]] = itertools.chain(
                guild.members, f
            )

            maybe_matches = []
            for obj in objects:
                if obj.name == argument or str(obj) == argument:
                    maybe_matches.append(obj)

                maybe_nick = getattr(obj, "nick", None)
                if maybe_nick is not None and maybe_nick == argument:
                    maybe_matches.append(obj)

            if not maybe_matches:
                raise commands.BadArgument(
                    f"'{argument}' was not found. It must be the ID, mention,"
                    " or name of a channel, user or role in this server."
                )
            if len(maybe_matches) == 1:
                return maybe_matches[0]
            raise commands.BadArgument(
                f"'{argument}' does not refer to a unique channel, user or role."
                " Please use the ID for whatever/whoever"
                " you're trying to specify, or mention it/them."
            )


if TYPE_CHECKING:
    MemberOrRoleOrVocalChannel = Union[
        discord.VoiceChannel, discord.StageChannel, discord.Member, discord.Role
    ]
else:

    class MemberOrRoleOrVocalChannel:
        @classmethod
        async def convert(
            cls, ctx: GuildContext, argument: str
        ) -> Union[
            discord.VoiceChannel, discord.StageChannel, discord.Member, discord.Role
        ]:
            guild: discord.Guild = ctx.guild
            _id = _match_id(argument)

            if _id is not None:
                channel: Optional[discord.abc.GuildChannel] = guild.get_channel(_id)
                if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                    return channel

                member: Optional[discord.Member] = guild.get_member(_id)
                if member is not None:
                    return member

                role: Optional[discord.Role] = guild.get_role(_id)
                if role is not None and not role.is_default():
                    return role

            f = filter(lambda r: not r.is_default(), guild.roles)
            # wrong inferred type: https://github.com/python/mypy/issues/8226
            objects: Iterator[
                Union[
                    discord.VoiceChannel,
                    discord.StageChannel,
                    discord.Member,
                    discord.Role,
                ]
            ] = itertools.chain(
                guild.voice_channels, guild.stage_channels, guild.members, f
            )

            maybe_matches = []
            for obj in objects:
                if obj.name == argument or str(obj) == argument:
                    maybe_matches.append(obj)

                maybe_nick = getattr(obj, "nick", None)
                if maybe_nick is not None and maybe_nick == argument:
                    maybe_matches.append(obj)

            if not maybe_matches:
                raise commands.BadArgument(
                    f"'{argument}' was not found. It must be the ID, mention,"
                    " or name of a channel, user or role in this server."
                )
            if len(maybe_matches) == 1:
                return maybe_matches[0]
            raise commands.BadArgument(
                f"'{argument}' does not refer to a unique channel, user or role."
                " Please use the ID for whatever/whoever you're trying to specify,"
                " or mention it/them."
            )
