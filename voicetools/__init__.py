from redbot import version_info, VersionInfo
from redbot.core.bot import Red
from redbot.core.errors import CogLoadError

from .voicetools import VoiceTools


async def setup(bot: Red) -> None:
    if version_info < VersionInfo.from_str("3.1.3"):
        raise CogLoadError(
            "This cog requires at least Red 3.1.3.\n"
            "Go update, it's a straight improvement from previously supported versions."
        )
    bot.add_cog(VoiceTools())
