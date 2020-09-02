# Copyright 2018-2020 Jakub Kuczys (https://github.com/jack1142)
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

from typing import Any, Awaitable, Callable, Dict, List, Optional, Union, cast

import discord
from redbot.cogs.downloader.downloader import Downloader  # DEP-WARN
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
    [
        commands.Context,
        Union[List[str], List[discord.Embed]],
        Dict[Any, Callable[..., Awaitable[Any]]],
        discord.Message,
        int,
        float,
        str,
    ],
    Awaitable[Any],
]:
    async def install_cog(
        ctx: commands.Context,
        pages: Union[List[str], List[discord.Embed]],
        controls: Dict[Any, Callable[..., Awaitable[Any]]],
        message: discord.Message,
        page: int,
        timeout: float,
        emoji: str,
    ) -> Any:
        cog_item = cogs[page]
        if (repo_item := repo_list.get(cog_item["repo_name"])) is None:
            await ctx.send("Error: The repo for this cog is unknown.")
            return menu(ctx, pages, controls, message, page, timeout)

        downloader = cast(Optional[Downloader], ctx.bot.get_cog("Downloader"))
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
            result = cast(bool, pred.result)
            if not result:
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
        # Red isn't typed that well (+ this is recursive type),
        # and I don't want to deal with this
        controls = DEFAULT_CONTROLS  # type: ignore[assignment]

    return menu(ctx, pages, controls)
