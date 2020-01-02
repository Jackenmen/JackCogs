from redbot.core.bot import Red

from .membercount import MemberCount


def setup(bot: Red) -> None:
    bot.add_cog(MemberCount())
