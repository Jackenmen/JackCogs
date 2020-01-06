from redbot.core.bot import Red

from .nitrorole import NitroRole


async def setup(bot: Red) -> None:
    bot.add_cog(NitroRole(bot))
