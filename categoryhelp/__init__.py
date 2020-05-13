from redbot.core.bot import Red

from .categoryhelp import CategoryHelp


def setup(bot: Red) -> None:
    cog = CategoryHelp(bot)
    bot.add_cog(cog)
