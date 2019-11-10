from redbot.core.bot import Red

from .rlstats import RLStats


async def setup(bot: Red) -> None:
    cog = RLStats(bot)
    await cog.initialize()
    bot.add_cog(cog)
