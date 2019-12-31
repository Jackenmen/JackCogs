from redbot.core.bot import Red
from redbot.core.errors import CogLoadError

try:
    from .rlstats import RLStats
except ModuleNotFoundError as e:
    if e.name == "PIL":
        raise CogLoadError(
            "You need `pillow` pip package to run this cog."
            " Downloader *should* have handled this for you."
        )
    if e.name == "rlapi":
        raise CogLoadError(
            "You need `rlapi` pip package to run this cog."
            " Downloader *should* have handled this for you."
        )
    raise


async def setup(bot: Red) -> None:
    cog = RLStats(bot)
    await cog.initialize()
    bot.add_cog(cog)
