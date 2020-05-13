from __future__ import annotations

from typing import Dict, List, Optional

from redbot.core import commands
from redbot.core.bot import Red


class CategoryHelp(commands.Cog):
    """Command for getting help for category that ignores case-sensitivity."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot

    @property
    def categories(self) -> Dict[str, List[commands.Cog]]:
        """Case-insensitive categories."""
        cats: Dict[str, List[commands.Cog]] = {}
        for cog_name, cog in self.bot.cogs.items():
            cats.setdefault(cog_name.lower(), []).append(cog)
        return cats

    def get_cog(self, name: str) -> Optional[commands.Cog]:
        """Get cog with given name (with case-insensitive support)."""
        if (exact_match := self.bot.get_cog(name)) is not None:
            return exact_match
        cogs = self.categories.get(name)
        if cogs:
            # TODO: allow to choose the cog if multiple matches found
            return cogs[0]
        return None

    @commands.command()
    async def categoryhelp(self, ctx: commands.Context, *, category_name: str) -> None:
        """Get help for category."""
        if (cog := self.get_cog(category_name)) is None:
            # TODO: make it like help formatter's "Help topic for ... not found."
            await ctx.send("This category doesn't exist!")
            return
        await self.bot.send_help_for(ctx, cog)
