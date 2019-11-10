import itertools
import re
from typing import Optional, Union

import discord
from redbot.core import commands

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


class MemberOrRole(commands.Converter):
    async def convert(
        self, ctx: commands.Context, arg: str
    ) -> Union[discord.Member, discord.Role]:
        guild: discord.Guild = ctx.guild
        _id = _match_id(arg)

        if _id is not None:
            member: discord.Member = guild.get_member(_id)
            if member is not None:
                return member

            role: discord.Role = guild.get_role(_id)
            if role is not None and not role.is_default():
                return role

        objects = itertools.chain(
            guild.members, filter(lambda r: not r.is_default(), guild.roles)
        )

        maybe_matches = []
        for obj in objects:
            if obj.name == arg or str(obj) == arg:
                maybe_matches.append(obj)
            try:
                if obj.nick == arg:
                    maybe_matches.append(obj)
            except AttributeError:
                pass

        if not maybe_matches:
            raise commands.BadArgument(
                f"'{arg}' was not found. It must be the ID, mention,"
                " or name of a channel, user or role in this server."
            )
        if len(maybe_matches) == 1:
            return maybe_matches[0]
        raise commands.BadArgument(
            f"'{arg}' does not refer to a unique channel, user or role."
            " Please use the ID for whatever/whoever"
            " you're trying to specify, or mention it/them."
        )


class MemberOrRoleorVoiceChannel(commands.Converter):
    async def convert(
        self, ctx: commands.Context, arg: str
    ) -> Union[discord.VoiceChannel, discord.Member, discord.Role]:
        guild: discord.Guild = ctx.guild
        _id = _match_id(arg)

        if _id is not None:
            channel: discord.abc.GuildChannel = guild.get_channel(_id)
            if isinstance(channel, discord.VoiceChannel):
                return channel

            member: discord.Member = guild.get_member(_id)
            if member is not None:
                return member

            role: discord.Role = guild.get_role(_id)
            if role is not None and not role.is_default():
                return role

        objects = itertools.chain(
            guild.voice_channels,
            guild.members,
            filter(lambda r: not r.is_default(), guild.roles),
        )

        maybe_matches = []
        for obj in objects:
            if obj.name == arg or str(obj) == arg:
                maybe_matches.append(obj)
            try:
                if obj.nick == arg:
                    maybe_matches.append(obj)
            except AttributeError:
                pass

        if not maybe_matches:
            raise commands.BadArgument(
                f"'{arg}' was not found. It must be the ID, mention,"
                " or name of a channel, user or role in this server."
            )
        if len(maybe_matches) == 1:
            return maybe_matches[0]
        raise commands.BadArgument(
            f"'{arg}' does not refer to a unique channel, user or role."
            " Please use the ID for whatever/whoever you're trying to specify,"
            " or mention it/them."
        )
