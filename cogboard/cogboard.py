import re
import time
from typing import Dict, List, Tuple, Union

import aiohttp
import discord
import fuzzywuzzy.process
import fuzzywuzzy.utils
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.config import Config
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu
from typing_extensions import TypedDict
from yarl import URL

from . import errors


class RepoItem(TypedDict):
    author: str
    repo_url: str
    branch: str
    repo_name: str


class CogItem(TypedDict):
    repo_name: str
    name: str
    description: str


class CogBoard(commands.Cog):
    """Search for cogs in approved repos on CogBoard."""

    REPOS_POST = "https://cogboard.red/posts/533.json"
    REPOS_REGEX = re.compile(
        r"""
        ^(?!\|-+\|)  # skip table header
        \|\ *(?P<author>[^|]*[^ |])\ *
        \|\ *(?P<repo_name>[^|]*[^ |])\ *
        \|\ *(?P<repo_url>[^|]*[^ |])\ *
        \|\ *(?P<branch>[^\n|]*[^ \n|])\ *
        $
        """,
        re.VERBOSE | re.MULTILINE,
    )
    COG_LIST_REGEX = re.compile(
        r"""
        \n_{29}\n
        \*{2}(?P<repo_name>[^\n*]*)\*{2}
        \n{2}(?P<cog_list>.*?(?=\n{2,}))
        """,
        re.VERBOSE | re.DOTALL,
    )

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=176070082584248320, force_registration=True
        )
        self.config.register_global(
            repo_list={}, cog_list=[], last_update=0, cache_expire=3600
        )
        self.session = aiohttp.ClientSession()

    def cog_unload(self) -> None:
        self.session.detach()

    __del__ = cog_unload

    async def get_repos_and_cogs(
        self, *, force_refresh: bool = False
    ) -> Tuple[Dict[str, RepoItem], List[CogItem]]:
        cfg = await self.config.all()
        current_time = int(time.time())
        last_update, cache_expire = cfg["last_update"], cfg["cache_expire"]
        if current_time - last_update < cache_expire and not force_refresh:
            return cfg["repo_list"], cfg["cog_list"]
        try:
            async with self.session.get(self.REPOS_POST) as resp:
                if resp.status != 200:
                    raise errors.HTTPException(resp)
                raw_content: str = (await resp.json())["raw"]
        except (aiohttp.ClientConnectionError, errors.HTTPException):
            if force_refresh:
                raise errors.CacheRefreshFailed()
            # fallback to cache
            return cfg["repo_list"], cfg["cog_list"]
        await self.config.last_update.set(current_time)
        repo_list: Dict[str, RepoItem] = {}
        cog_list: List[CogItem] = []
        start_index = 0
        for match in self.REPOS_REGEX.finditer(raw_content):
            repo_url = match.group("repo_url")
            repo: RepoItem = {
                "author": match.group("author"),
                "repo_url": repo_url,
                "branch": match.group("branch"),
                "repo_name": match.group("repo_name"),
            }
            repo_list[URL(repo_url.rstrip("/")).name] = repo
            start_index = match.end()
        for match in self.COG_LIST_REGEX.finditer(raw_content, start_index):
            repo_name = match.group("repo_name")
            for cog_info in match.group("cog_list").splitlines():
                cog_name, _, cog_description = cog_info[2:].partition(": ")
                cog_list.append(
                    {
                        "repo_name": repo_name,
                        "name": cog_name,
                        "description": cog_description,
                    }
                )
        await self.config.repo_list.set(repo_list)
        await self.config.cog_list.set(cog_list)
        return repo_list, cog_list

    @commands.group()
    async def cogboard(self, ctx: commands.Context) -> None:
        """CogBoard commands."""

    @cogboard.command(name="refreshcache")
    @commands.is_owner()
    async def cogboard_refreshcache(self, ctx: commands.Context) -> None:
        """Refresh CogBoard cache."""
        failed = False
        async with ctx.typing():
            try:
                await self.get_repos_and_cogs(force_refresh=True)
            except errors.CacheRefreshFailed:
                failed = True
        if failed:
            await ctx.send("CogBoard cache refresh failed.")
        else:
            await ctx.send("CogBoard cache refreshed.")

    @cogboard.command(name="updateevery")
    @commands.is_owner()
    async def cogboard_cacheexpire(
        self, ctx: commands.Context, expire_time: int
    ) -> None:
        """Set cache expire time (in seconds)"""
        if expire_time < 0:
            await ctx.send("Cache expire time can't be negative!")
            return
        await self.config.cache_expire.set(expire_time)
        await ctx.send(f"Cache expire time set to {expire_time} seconds.")

    @cogboard.command(name="search")
    async def cogboard_search(self, ctx: commands.Context, query: str) -> None:
        """Find cog on CogBoard by name."""
        async with ctx.typing():
            repo_list, cog_list = await self.get_repos_and_cogs()
            name_matches = fuzzywuzzy.process.extract(
                {"name": query},
                cog_list,
                processor=lambda c: fuzzywuzzy.utils.full_process(c["name"]),
            )
            desc_matches = fuzzywuzzy.process.extract(
                {"description": query},
                cog_list,
                processor=lambda c: fuzzywuzzy.utils.full_process(c["description"]),
            )
            best_matches = sorted(
                name_matches + desc_matches, key=lambda m: m[1], reverse=True
            )
            pages = []
            # I don't like how `[p]embedset` currently works, using regular perm check
            use_embeds = ctx.channel.permissions_for(ctx.me).embed_links
            if use_embeds:
                embed_color = await ctx.embed_color()
            page: Union[discord.Embed, str]
            for match in best_matches:
                cog = match[0]
                repo = repo_list.get(
                    cog["repo_name"],
                    {
                        "author": "Unknown",
                        "repo_url": "Unknown",
                        "branch": "Unknown",
                        "repo_name": cog["repo_name"],
                    },
                )
                if use_embeds:
                    page = discord.Embed(title=cog["name"], color=embed_color)
                    page.add_field(
                        name="Description", value=cog["description"], inline=False
                    )
                    page.add_field(name="Author", value=repo["author"], inline=False)
                    page.add_field(
                        name="Repo url", value=repo["repo_url"], inline=False
                    )
                    page.add_field(name="Branch", value=repo["branch"], inline=False)
                else:
                    page = (
                        f"```asciidoc\n"
                        f"= {cog['name']} =\n"
                        f"* Description:\n"
                        f"  {cog['description']}\n"
                        f"* Author:\n"
                        f"  {repo['author']}\n"
                        f"* Repo url:\n"
                        f"  {repo['repo_url']}\n"
                        f"* Branch:\n"
                        f"  {repo['branch']}\n"
                        f"```"
                    )
                pages.append(page)
        await menu(ctx, pages, DEFAULT_CONTROLS)
