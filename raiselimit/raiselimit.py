from redbot.core import commands


class RaiseLimit(commands.Cog):
    """Raises limit of users in voice channel, when bot joins."""

    async def on_voice_state_update(self, member, before, after):
        """ If bot joins/leaves a channel with user limit, modify it accordingly"""
        if member is member.guild.me and before.channel is not after.channel:
            if before.channel is not None and before.channel.user_limit != 0:
                await before.channel.edit(user_limit=before.channel.user_limit-1)
            if after.channel is not None and after.channel.user_limit != 0:
                await after.channel.edit(user_limit=after.channel.user_limit+1)
