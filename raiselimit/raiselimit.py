import discord
from discord.ext import commands

class RaiseLimit:
    """Raises limit of users in voice channel, when bot joins."""
    
    def __init__(self, bot):
        self.bot = bot
        
    async def _on_voice_state_update(self, before, after):
        """ If event is about bot and change of channels, change user limit respectively """
        if after is after.server.me and before.voice.voice_channel is not after.voice.voice_channel:
            if before.voice.voice_channel is not None and before.voice.voice_channel.user_limit is not 0:
                try:
                    await self.bot.edit_channel(before.voice.voice_channel, user_limit=before.voice.voice_channel.user_limit-1)
                except discord.Forbidden:
                    print("I don't have permission to edit the channel!")
                except discord.HTTPException as err:
                    print("An unexpected error occured. Probably discord API timed out, so probably you can just wait some time, but if the error repeats here's some useful info for debugging error:\n{}".format(err))
            if after.voice.voice_channel is not None and after.voice.voice_channel.user_limit is not 0:
                try:
                    await self.bot.edit_channel(after.voice.voice_channel, user_limit=after.voice.voice_channel.user_limit+1)
                except discord.Forbidden:
                    print("I don't have permission to edit the channel!")
                except discord.HTTPException as err:
                    print("An unexpected error occured. Probably discord API timed out, so probably you can just wait some time, but if the error repeats here's some useful info for debugging error:\n{}".format(err))
    
def setup(bot):
    n = RaiseLimit(bot)
    bot.add_listener(n._on_voice_state_update, 'on_voice_state_update')
    bot.add_cog(n)