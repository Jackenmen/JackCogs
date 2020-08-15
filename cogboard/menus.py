from typing import Any, Awaitable, Callable, Dict, List, Union

import discord
from redbot.core import commands
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu, start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

from .downloader_integration import get_repo_by_url
from .typings import CogItem, RepoItem
from .utils import get_fake_context

DOWNWARDS_ARROW = "\N{DOWNWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}"


def _make_install_cog_func(
    cogs: List[CogItem], repo_list: Dict[str, RepoItem]
) -> Callable[
    [commands.Context, list, dict, discord.Message, int, float, str], Awaitable[Any]
]:
    async def install_cog(
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float,
        emoji: str,
    ) -> Any:
        cog_item = cogs[page]
        if (repo_item := repo_list.get(cog_item["repo_name"])) is None:
            await ctx.send("Error: The repo for this cog is unknown.")
            return menu(ctx, pages, controls, message, page, timeout)

        downloader = ctx.bot.get_cog("Downloader")
        if downloader is None:
            await ctx.send("Error: Downloader is not loaded.")
            return menu(ctx, pages, controls, message, page, timeout)

        url = repo_item["repo_url"]
        if (repo := get_repo_by_url(downloader, url)) is None:
            msg = await ctx.send(
                "Error: Repository with this URL couldn't have been found.\n"
                "Do you want to add it?"
            )
            start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(msg, ctx.author)
            await ctx.bot.wait_for("reaction_add", check=pred)
            if not pred.result:
                return menu(ctx, pages, controls, message, page, timeout)

            command = downloader._repo_add
            fake_context = await get_fake_context(ctx, command)

            branch = branch if (branch := repo_item["branch"]) != "-" else None
            await command(fake_context, repo_item["repo_name"], url, branch)
            if (repo := get_repo_by_url(downloader, url)) is None:
                await ctx.send(
                    "Error: I couldn't find the repo after adding it to Downloader."
                )
                return menu(ctx, pages, controls, message, page, timeout)

        await downloader._cog_install(ctx, repo, cog_item["name"])

        return menu(ctx, pages, controls, message, page, timeout)

    return install_cog


def construct_menu(
    ctx: commands.Context,
    pages: Union[List[str], List[discord.Embed]],
    cogs: List[CogItem],
    repo_list: Dict[str, RepoItem],
    *,
    allow_install: bool = False,
) -> Awaitable[Any]:
    if allow_install:
        controls = {
            **DEFAULT_CONTROLS,
            DOWNWARDS_ARROW: _make_install_cog_func(cogs, repo_list),
        }
    else:
        controls = DEFAULT_CONTROLS

    return menu(ctx, pages, controls)
