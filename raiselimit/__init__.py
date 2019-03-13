from .raiselimit import RaiseLimit


async def setup(bot):
    bot.add_cog(RaiseLimit())
