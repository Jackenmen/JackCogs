from redbot.core.bot import Red

from .linkwarner import LinkWarner


async def setup(bot: Red):
    cog = LinkWarner(bot)
    await cog.initialize()
    bot.add_cog(cog)
