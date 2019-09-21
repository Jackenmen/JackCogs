from .mee6rank import Mee6Rank


async def setup(bot):
    bot.add_cog(Mee6Rank(bot))
