from .rlstats import RLStats


async def setup(bot):
    cog = RLStats(bot)
    await cog.initialize()
    bot.add_cog(cog)
