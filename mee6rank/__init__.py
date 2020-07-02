from redbot.core.bot import Red

from .mee6rank import Mee6Rank


async def setup(bot: Red) -> None:
    bot.add_cog(Mee6Rank(bot))
