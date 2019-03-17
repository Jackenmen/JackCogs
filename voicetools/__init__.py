from .voicetools import VoiceTools


async def setup(bot):
    bot.add_cog(VoiceTools())
