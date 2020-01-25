from redbot.core.bot import Red
from redbot.core.errors import CogLoadError

try:
    from .cogboard import CogBoard
except ModuleNotFoundError as e:
    if e.name == "typing_extensions":
        raise CogLoadError(
            "You need `typing_extensions` pip package to run this cog."
            " Downloader *should* have handled this for you."
        )
    raise


def setup(bot: Red) -> None:
    bot.add_cog(CogBoard(bot))
