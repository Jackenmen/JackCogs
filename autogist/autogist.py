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

import contextlib
from io import BytesIO
from typing import Any, Dict, Literal, Mapping, MutableMapping, Tuple

import aiohttp
import cachetools
import discord
import gidgethub
import gidgethub.aiohttp
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands import GuildContext, NoParseOptional as Optional
from redbot.core.config import Config
from redbot.core.utils import can_user_send_messages_in
from redbot.core.utils.chat_formatting import humanize_list, inline
from redbot.core.utils.views import SetApiView

from .discord_utils import (
    GuildMessageable,
    fetch_attachment_from_message,
    safe_raw_edit,
)
from .errors import HandledHTTPError
from .guild_data import GuildData
from .log import log

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]

MAX_SIZE = 2 * 1024 * 1024


class AutoGist(commands.Cog):
    """Auto-upload files with configured extension sent by users to gist.github.com."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self._session: aiohttp.ClientSession
        self.config = Config.get_conf(self, 176070082584248320, force_registration=True)
        self.config.register_guild(
            blocklist_mode=False,
            file_extensions=[".txt", ".log"],
            listen_to_humans=True,
            listen_to_bots=False,
            listen_to_self=False,
        )
        # state:
        #  - `True` - allowed
        #  - `False` - blocked
        #  - `None` - not set (the default)
        self.config.register_channel(state=None)
        # gists:
        #  list of IDs of all uploaded gists for the files uploaded by user
        #  the only purpose of this are data deletion requests
        self.config.register_user(gists=[])
        # message_cache:
        #  {message_id: (user_id, gist_id, bot_message_id)}
        self._message_cache: MutableMapping[
            int, Tuple[int, str, int]
        ] = cachetools.Cache(maxsize=10_000)
        self._guild_cache: Dict[int, GuildData] = {}

    async def initialize(self) -> None:
        self._session = aiohttp.ClientSession()
        self.gh = gidgethub.aiohttp.GitHubAPI(
            session=self._session,
            requester="AutoGist cog for Red-DiscordBot",
            oauth_token=await self._get_token(),
        )

    async def cog_unload(self) -> None:
        await self._session.close()

    async def red_get_data_for_user(self, *, user_id: int) -> Dict[str, BytesIO]:
        gists = await self.config.user_from_id(user_id).gists()
        if not gists:
            return {}

        gist_links = "\n".join(
            f"- https://gist.github.com/{gist_id}" for gist_id in gists
        )
        contents = (
            f"Links below are all text attachments from your messages"
            f" that were uploaded to gist.github.com.\n{gist_links}"
        )
        return {"user_data.txt": BytesIO(contents.encode())}

    async def red_delete_data_for_user(
        self, *, requester: RequestType, user_id: int
    ) -> None:
        # This is interacting with external API
        # and this may result in errors requiring bot owner intervention.
        #
        # Due to that, data deletion request can currently only be made by bot owner.
        #
        # Considering the scope of this (invalidating gist links in old messages),
        # it's probably better this way even if we ignore the external API issue.
        #
        # Perhaps `user_strict` could also be clearing gists,
        # but it's not crucial.
        if requester not in ("discord_deleted_user", "owner"):
            return

        user_scope = self.config.user_from_id(user_id)

        gists = await user_scope.gists()
        failed = []
        for gist_id in gists:
            try:
                await self._request("delete", "/gists/{gist_id}", {"gist_id": gist_id})
            except HandledHTTPError:
                failed.append(gist_id)

        await user_scope.clear()

        if failed:
            gist_links = "\n".join(
                f"- https://gist.github.com/{gist_id}" for gist_id in failed
            )
            # That seems like a reasonable way to handle failures
            raise RuntimeError(
                f"Failed to remove gists linked below for user with ID {user_id}:\n"
                f"{gist_links}\n\n"
                "See the earlier log entries for the relevant HTTP errors.\n"
                "AutoGist has removed all the other data for the user successfully."
            )

    async def get_guild_data(self, guild: discord.Guild) -> GuildData:
        try:
            return self._guild_cache[guild.id]
        except KeyError:
            pass

        data = await GuildData.from_guild(self.bot, self.config, guild)
        self._guild_cache[guild.id] = data

        return data

    async def _get_token(
        self, api_tokens: Optional[Mapping[str, str]] = None
    ) -> Optional[str]:
        """Get GitHub token."""
        if api_tokens is None:
            api_tokens = await self.bot.get_shared_api_tokens("github")

        token = api_tokens.get("token") or None
        if token is None:
            log.error("No valid token found")
        return token

    @commands.admin_or_permissions(manage_guild=True)
    @commands.group()
    async def autogistset(self, ctx: GuildContext) -> None:
        """AutoGist settings."""

    @commands.is_owner()
    @autogistset.command(name="token")
    async def autogistset_token(self, ctx: commands.Context) -> None:
        """Instructions to set the GitHub API token."""
        message = (
            "Begin by creating a new personal token on your GitHub Account here:\n"
            "<https://github.com/settings/tokens>\n"
            "If you do not trust this to your own account,"
            " it's recommended that you make a new GitHub account to act for the bot.\n"
            "This cog requires gist permissions,"
            " so you will need to select `gist` scope for the token.\n\n"
            "When you generate the token, copy it"
            " and click the button below to set your token."
        )
        await ctx.send(
            message,
            view=SetApiView(default_service="github", default_keys={"token": ""}),
        )

    @commands.guild_only()
    @autogistset.command(name="channeldefault")
    async def autogistset_channeldefault(
        self, ctx: GuildContext, allow: Optional[bool] = None
    ) -> None:
        """
        Set whether AutoGist should by default listen to channels.

        If default is set to True, bot will only listen to channels it was explicitly
        allowed to listen to with `[p]autogistset allowchannels` command.

        If default is set to False, bot will listen to all channels except the ones
        it was explicitly blocked from listening to
        with `[p]autogistset denychannels` command.

        By default, guilds will not listen to any channel.
        Use `[p]autogist channeldefault` without a setting to see current mode.
        """
        guild_data = await self.get_guild_data(ctx.guild)
        if allow is None:
            if guild_data.blocklist_mode:
                msg = "AutoGist listens to channels in this server by default."
            else:
                msg = "AutoGist doesn't listen to channels in this server by default."
            await ctx.send(msg)
            return

        if guild_data.blocklist_mode is allow:
            if allow:
                msg = "AutoGist already listens to channels in this server by default."
            else:
                msg = (
                    "AutoGist already doesn't listen to channels"
                    " in this server by default."
                )
            await ctx.send(msg)
            return

        await guild_data.edit_blocklist_mode(allow)
        if allow:
            msg = "AutoGist will now listen to channels in this server by default."
        else:
            msg = "AutoGist will now not listen to channels in this server by default."
        await ctx.send(msg)

    @commands.guild_only()
    @autogistset.command(
        name="allowchannels", aliases=["allowchannel"], usage="<channels...>"
    )
    async def autogistset_allowchannels(
        self, ctx: GuildContext, *channels: GuildMessageable
    ) -> None:
        """Allow the bot to listen to the given channels."""
        if not channels:
            await ctx.send_help()
            return
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.update_channel_states(channels, True)
        await ctx.send("Bot will now listen to the messages in given channels.")

    @commands.guild_only()
    @autogistset.command(
        name="blockchannels", aliases=["blockchannel"], usage="<channels...>"
    )
    async def autogistset_blockchannels(
        self, ctx: GuildContext, *channels: GuildMessageable
    ) -> None:
        """Block the bot from listening to the given channels."""
        if not channels:
            await ctx.send_help()
            return
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.update_channel_states(channels, False)
        await ctx.send("Bot will no longer listen to the messages in given channels.")

    @commands.guild_only()
    @autogistset.command(name="listoverridden")
    async def autogistset_listoverridden(self, ctx: GuildContext) -> None:
        """List guild channels that don't use the default setting."""
        guild_data = await self.get_guild_data(ctx.guild)
        overridden = [
            channel.mention
            for channel in ctx.guild.text_channels
            if await guild_data.is_overridden(channel)
        ]

        if not overridden:
            await ctx.send("There are no channels with overridden setting.")
            return

        # Who cares about plural support, right? :P
        if guild_data.blocklist_mode:
            msg = "AutoGist will not listen to messages in these channels:\n"
        else:
            msg = "AutoGist will listen to messages in these channels:\n"
        await ctx.send(f"{msg}{humanize_list(overridden)}")

    @commands.guild_only()
    @autogistset.command(name="listentohumans")
    async def autogistset_listentohumans(
        self, ctx: GuildContext, state: Optional[bool] = None
    ) -> None:
        """Make AutoGist listen to messages from humans in this server."""
        guild_data = await self.get_guild_data(ctx.guild)
        if state is None:
            if guild_data.listen_to_humans:
                msg = "AutoGist listens to messages from humans in this server."
            else:
                msg = "AutoGist doesn't listen to messages from humans in this server."
            await ctx.send(msg)
            return

        if state is guild_data.listen_to_humans:
            if state:
                msg = "AutoGist already listens to messages from humans in this server."
            else:
                msg = (
                    "AutoGist already doesn't listen to messages"
                    " from humans in this server."
                )
            await ctx.send(msg)
            return

        await guild_data.edit_listen_to_humans(state)
        if state:
            msg = "AutoGist will now listen to messages from humans in this server."
        else:
            msg = (
                "AutoGist will no longer listen to messages from humans in this server."
            )
        await ctx.send(msg)

    @commands.guild_only()
    @autogistset.command(name="listentobots")
    async def autogistset_listentobots(
        self, ctx: GuildContext, state: Optional[bool] = None
    ) -> None:
        """
        Make AutoGist listen to messages from other bots in this server.

        NOTE: To make bot listen to messages from itself,
        you need to use `[p]autogistset listentoself` command.
        """
        guild_data = await self.get_guild_data(ctx.guild)
        if state is None:
            if guild_data.listen_to_bots:
                msg = "AutoGist listens to messages from other bots in this server."
            else:
                msg = (
                    "AutoGist doesn't listen to messages"
                    " from other bots in this server."
                )
            await ctx.send(msg)
            return

        if state is guild_data.listen_to_bots:
            if state:
                msg = (
                    "AutoGist already listens to messages"
                    " from other bots in this server."
                )
            else:
                msg = (
                    "AutoGist already doesn't listen to messages"
                    " from other bots in this server."
                )
            await ctx.send(msg)
            return

        await guild_data.edit_listen_to_bots(state)
        if state:
            msg = "AutoGist will now listen to messages from other bots in this server."
        else:
            msg = (
                "AutoGist will no longer listen to messages"
                " from other bots in this server."
            )
        await ctx.send(msg)

    @commands.guild_only()
    @autogistset.command(name="listentoself")
    async def autogistset_listentoself(
        self, ctx: GuildContext, state: Optional[bool] = None
    ) -> None:
        """
        Make the bot listen to messages from itself in this server.

        See also: `[p]autogistset listentobots` command,
        that makes the bot listen to other bots.
        """
        guild_data = await self.get_guild_data(ctx.guild)
        if state is None:
            if guild_data.listen_to_self:
                msg = "AutoGist listens to messages from its bot user in this server."
            else:
                msg = (
                    "AutoGist doesn't listen to messages"
                    " from its bot user in this server."
                )
            await ctx.send(msg)
            return

        if state is guild_data.listen_to_self:
            if state:
                msg = (
                    "AutoGist already listens to messages"
                    " from its bot user in this server."
                )
            else:
                msg = (
                    "AutoGist already doesn't listen to messages"
                    " from its bot user in this server."
                )
            await ctx.send(msg)
            return

        await guild_data.edit_listen_to_self(state)
        if state:
            msg = (
                "AutoGist will now listen to messages from its bot user in this server."
            )
        else:
            msg = (
                "AutoGist will no longer listen to messages"
                " from its bot user in this server."
            )
        await ctx.send(msg)

    @commands.guild_only()
    @autogistset.group(name="extensions", aliases=["ext", "exts"])
    async def autogistset_extensions(self, ctx: GuildContext) -> None:
        """
        Settings for file extensions
        that are required for AutoGist to upload file to Gist.

        By default AutoGist will look for files with `.txt` and `.log` extensions.
        """

    @autogistset_extensions.command(name="add", usage="<extensions...>")
    async def autogistset_extensions_add(
        self, ctx: GuildContext, *extensions: str
    ) -> None:
        """
        Add file extensions to the list.

        Example:
        `[p]autogist extensions add txt .log` - adds `.txt` and `.log` extensions.
        """
        if not extensions:
            await ctx.send_help()
            return
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.add_file_extensions(extensions)
        await ctx.send("Bot will now upload files with the given extensions.")

    @autogistset_extensions.command(
        name="remove", aliases=["delete"], usage="<extensions...>"
    )
    async def autogistset_extensions_remove(
        self, ctx: GuildContext, *extensions: str
    ) -> None:
        """
        Remove file extensions from the list.

        Example:
        `[p]autogist extensions remove txt .log` - removes `.txt` and `.log` extensions.
        """
        if not extensions:
            await ctx.send_help()
            return
        guild_data = await self.get_guild_data(ctx.guild)
        await guild_data.remove_file_extensions(extensions)
        await ctx.send("Bot will now no longer upload files with the given extensions.")

    @autogistset_extensions.command(name="list")
    async def autogistset_extensions_list(self, ctx: GuildContext) -> None:
        """
        List file extensions that are required for AutoGist to upload file to Gist.
        """
        guild_data = await self.get_guild_data(ctx.guild)
        msg = "AutoGist will upload files with these extensions to Gist:\n"
        extensions = humanize_list(list(map(inline, guild_data.file_extensions)))
        await ctx.send(f"{msg}{extensions}")

    async def _should_ignore(self, message: discord.Message) -> bool:
        """
        Checks whether message should be ignored in the `on_message` listener.

        This checks whether:
        - OAuth token has been set
        - message has been sent in guild
        - message author is allowed by Red's allowlist and blocklist
        - cog is disabled in guild
        - bot has permissions to send messages in the channel message was sent in
        - channel is permitted by cog's allowlist/blocklist
        - message has exactly one attachment
        - attachment's size isn't bigger than `MAX_SIZE`
        - extension of the attachment's filename matches guild's configured extensions

        Returns
        -------
        bool
            `True` if message should be ignored, `False` otherwise
        """
        guild = message.guild
        channel = message.channel

        if self.gh.oauth_token is None:
            return True

        if guild is None or isinstance(channel, discord.PartialMessageable):
            return True
        assert isinstance(channel, (discord.abc.GuildChannel, discord.Thread))

        if not await self.bot.allowed_by_whitelist_blacklist(message.author):
            return True

        if await self.bot.cog_disabled_in_guild(self, guild):
            return True

        if not can_user_send_messages_in(guild.me, channel):
            return True

        guild_data = await self.get_guild_data(guild)
        if not guild_data.is_permitted(message.author):
            return True

        if not await guild_data.is_enabled_for_channel(channel):
            return True

        if len(message.attachments) != 1:
            return True

        attachment = message.attachments[0]

        if attachment.size > MAX_SIZE:
            return True

        filename = attachment.filename.lower()
        if not filename.endswith(guild_data.file_extensions):
            return True

        return False

    async def _request(
        self,
        method: Literal["post", "delete"],
        url: str,
        url_vars: Dict[str, str] = {},
        **kwargs: Any,
    ) -> Any:
        """
        Make a GitHub API request using gidgethub.

        Follows the spec of given gidgethub method.

        Raises
        ------
        HandledHTTPError
            When GitHub API request didn't succeed.
            This is used as an indicator of failure
            and usually doesn't need additional handling.

        Returns
        -------
        Any
            Data returned by the specified ``method``.
        """
        func = getattr(self.gh, method)
        try:
            data = await func(url, url_vars, **kwargs)
        except gidgethub.RateLimitExceeded as e:
            log.warning(
                "Rate limit exceeded. Rate limit resets at %s",
                e.rate_limit.reset_datetime,
            )
            raise HandledHTTPError()
        except gidgethub.GitHubBroken as e:
            log.warning(
                "GitHub is having issues right now"
                " and couldn't process the request (status code: %s).",
                e.status_code,
                exc_info=e,
            )
            raise HandledHTTPError()
        except gidgethub.HTTPException as e:
            if e.status_code == 401:
                log.error("Set GitHub token is invalid.")
            elif e.status_code == 404:
                if method == "post":
                    log.error("Set GitHub token doesn't have `gist` scope.")
                else:
                    log.error(
                        "Gist with the given ID (%s) couldn't have been found"
                        " or the set GitHub token doesn't have access to it.",
                        url_vars.get("gist_id"),
                    )
            else:
                log.error("Unexpected error occurred (status code: %s).", exc_info=e)
            raise HandledHTTPError()

        return data

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Listens to messages with text attachments and uploads them to gist.
        """
        if await self._should_ignore(message):
            return

        assert message.guild is not None
        guild = message.guild
        author = message.author

        filename, content = await fetch_attachment_from_message(message)
        if not content:
            # content could not be decoded (is None) *or* the file is empty (== "")
            return

        try:
            data = await self._request(
                "post",
                "/gists",
                data={
                    "description": (
                        f"A file by {author} ({author.id})"
                        f" in the {guild.name} ({guild.id}) guild"
                    ),
                    "public": False,
                    "files": {filename: {"content": content}},
                },
            )
        except HandledHTTPError:
            # already handled in request method
            pass
        else:
            bot_message = await message.channel.send(
                f"File by {author} automatically uploaded to gist: <{data['html_url']}>"
            )
            gist_id = data["id"]
            self._message_cache[message.id] = (author.id, gist_id, bot_message.id)
            async with self.config.user(message.author).gists() as user_gists:
                # keeping this so that I can easily remove all gists
                user_gists.append(gist_id)

    @commands.Cog.listener()
    async def on_raw_message_delete(
        self, payload: discord.RawMessageDeleteEvent
    ) -> None:
        """
        Deletes gist and updates bot's message (the one with gist link),
        if deleted message has an entry in cog's message cache of gists.

        This is done to address privacy concerns of
        uploading contents of user-attached file to gist.
        """
        if (cached_data := self._message_cache.pop(payload.message_id, None)) is None:
            return

        user_id, gist_id, bot_message_id = cached_data

        msg_content = "The original message with the file has been removed."
        # already handled in request method
        try:
            await self._request("delete", "/gists/{gist_id}", {"gist_id": gist_id})
        except HandledHTTPError:
            pass
        else:
            msg_content += " Gist with that file has been deleted for privacy reasons."
            async with self.config.user_from_id(user_id).gists() as user_gists:
                # keeping this so that I can easily remove all gists
                with contextlib.suppress(ValueError):
                    user_gists.remove(gist_id)

        await safe_raw_edit(
            self.bot, payload.channel_id, bot_message_id, content=msg_content
        )

    @commands.Cog.listener()
    async def on_red_api_tokens_update(
        self, service_name: str, api_tokens: Mapping[str, str]
    ) -> None:
        """Update GitHub token when `[p]set api` command is used."""
        if service_name != "github":
            return
        self.gh.oauth_token = await self._get_token(api_tokens)
