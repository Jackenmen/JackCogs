from redbot.core.bot import Red

from .voicetools import VoiceTools


async def setup(bot: Red) -> None:
    bot.add_cog(VoiceTools())
