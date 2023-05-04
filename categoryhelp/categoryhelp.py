# Copyright 2018-present Jakub Kuczys (https://github.com/Jackenmen)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Literal, Optional, cast

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import bold, box
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]


class CategoryHelp(commands.Cog):
    """Command for getting help for category that ignores case-sensitivity."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot

    async def red_get_data_for_user(self, *, user_id: int) -> Dict[str, Any]:
        # this cog does not story any data
        return {}

    async def red_delete_data_for_user(
        self, *, requester: RequestType, user_id: int
    ) -> None:
        # this cog does not story any data
        pass

    @property
    def categories(self) -> Dict[str, List[commands.Cog]]:
        """Case-insensitive categories."""
        cats: Dict[str, List[commands.Cog]] = {}
        for cog_name, cog in self.bot.cogs.items():
            cats.setdefault(cog_name.lower(), []).append(cog)
        return cats

    def get_cogs(self, name: str) -> List[commands.Cog]:
        """Get cog with given name (with case-insensitive support)."""
        # TODO: prevent exact matches from skipping non-exact matches in returned list
        if (exact_match := self.bot.get_cog(name)) is not None:
            return [exact_match]
        cogs = self.categories.get(name.lower()) or []
        return cogs

    async def choose_cog(
        self, ctx: commands.Context, cogs: List[commands.Cog]
    ) -> Optional[commands.Cog]:
        """Ask user to choose a cog from provided `cogs` list."""
        if len(cogs) == 1:
            return cogs[0]
        cogs = sorted(cogs[:9], key=lambda cog: cog.qualified_name)
        emojis = ReactionPredicate.NUMBER_EMOJIS[1 : len(cogs) + 1]
        use_embeds = await ctx.embed_requested()

        lines = []
        if use_embeds:
            for idx, cog in enumerate(cogs, 1):
                cog_name = cog.qualified_name
                short_doc, *_ = cog.format_help_for_context(ctx).partition("\n\n")

                if len(short_doc) > 70:
                    short_doc = f"{short_doc[:67]}..."

                lines.append(f"{idx}. {bold(cog_name)} - {short_doc}")

            description = "\n".join(lines)
            embed = discord.Embed(
                title="There are multiple categories with provided name:",
                description=description,
            )
            msg = await ctx.send(embed=embed)
        else:
            # all cog names should have the same width since only casing differs
            doc_max_width = 80 - len(cogs[0].qualified_name)

            for idx, cog in enumerate(cogs, 1):
                cog_name = cog.qualified_name
                short_doc, *_ = cog.format_help_for_context(ctx).partition("\n\n")

                if len(short_doc) > doc_max_width:
                    short_doc = f"{short_doc[: doc_max_width - 3]}..."

                lines.append(f"{idx}. {cog_name}: {short_doc}")

            description = "\n".join(lines)
            msg = await ctx.send(
                f"There are multiple categories with provided name: {box(description)}"
            )

        start_adding_reactions(msg, emojis)
        pred = ReactionPredicate.with_emojis(emojis, msg)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
        except asyncio.TimeoutError:
            return None
        finally:
            await msg.delete()

        result = cast(int, pred.result)
        return cogs[result]

    @commands.command()
    async def categoryhelp(self, ctx: commands.Context, *, category_name: str) -> None:
        """Get help for category."""
        if not (cogs := self.get_cogs(category_name)):
            # TODO: make it like help formatter's "Help topic for ... not found."
            await ctx.send("This category doesn't exist!")
            return

        cog = await self.choose_cog(ctx, cogs)
        if cog is None:
            await ctx.send("Response timed out.")
            return

        await self.bot.send_help_for(ctx, cog)

    # TODO: add an alternative for full help command
    # I might want to wait on the help formatter work first, but I probably won't
    # settings needed for precedence rules
    # (e.g. skip choose menu for exact command/cog name matches)
