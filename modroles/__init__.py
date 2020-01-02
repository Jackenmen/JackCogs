from redbot.core.bot import Red

from .modroles import ModRoles


async def setup(bot: Red) -> None:
    bot.add_cog(ModRoles(bot))
