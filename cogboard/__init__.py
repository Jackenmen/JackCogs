from redbot.core.bot import Red

from .cogboard import CogBoard


def setup(bot: Red) -> None:
    bot.add_cog(CogBoard(bot))
