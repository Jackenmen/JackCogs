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
import datetime
import itertools
import logging
import random
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import aiohttp
import discord
import yarl
from discord.webhook.async_ import AsyncWebhookAdapter, async_context
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.config import Config
from redbot.core.utils.chat_formatting import inline, pagify
from redbot.core.utils.predicates import MessagePredicate
from redbot.core.utils.tunnel import Tunnel

IS_DISCORD = discord.utils.oauth_url("").startswith("https://discord.com/")
USER_MESSAGES = "USER_MESSAGES"
MESSAGES = "MESSAGES"
WEBHOOK_URL_RE = re.compile(
    r"https://(?P<base_url>.+)/webhooks"
    r"/(?P<id>[0-9]{17,20})/(?P<token>[A-Za-z0-9\.\-\_]{60,})"
)
VALID_BASE_URLS = (
    ("api.fluxer.app",) if IS_DISCORD else ("discord.com/api", "discordapp.com/api")
)

log = logging.getLogger("red.jackcogs.fluxerbridge")


class WebhookAdapter(AsyncWebhookAdapter):
    def __init__(self, base: str) -> None:
        super().__init__()
        self.__base = base

    async def request(  # type: ignore[no-untyped-def]
        self, route, *args: Any, **kwargs: Any
    ) -> Any:
        route.url = f"https://{self.__base}" + route.url[len(route.BASE) :]
        return await super().request(route, *args, **kwargs)


class Webhook(discord.Webhook):
    __slots__ = ("red_webhook_base_url",)

    red_webhook_base_url: str

    @property
    def url(self) -> str:
        """:class:`str` : Returns the webhook's url."""
        return f"https://{self.red_webhook_base_url}/webhooks/{self.id}/{self.token}"


class MessageEvent:
    def __init__(self, cog: FluxerBridge, /) -> None:
        self._cog = cog
        self._initialized = False
        self.finished = asyncio.Event()
        self.success = False

    async def init(self) -> None:
        if not self._initialized:
            await self._init()

    async def _init(self) -> None:
        pass

    async def execute(self) -> None:
        raise NotImplementedError(
            f"execute() method for {self.__class__} has not been implemented"
        )


class WebhookTestMessageEvent(MessageEvent):
    def __init__(self, cog: FluxerBridge, /, *, webhook_data: Dict[str, Any]) -> None:
        super().__init__(cog)
        self._webhook, self._thread = self._cog.get_webhook_from_data(webhook_data)
        self.last_error: Optional[Exception] = None

    async def execute(self) -> None:
        token = async_context.set(WebhookAdapter(self._webhook.red_webhook_base_url))
        try:
            await self._webhook.send(
                "A one-way bridge to this channel has been set up!",
                thread=self._thread,
                wait=True,
            )
        except discord.HTTPException as exc:
            self.last_error = exc
            raise
        finally:
            async_context.reset(token)


class MessageCreate(MessageEvent):
    def __init__(self, cog: FluxerBridge, /, *, message: discord.Message) -> None:
        super().__init__(cog)
        self.message = message

    async def execute(self) -> None:
        message = self.message
        if message.channel.id in self._cog.removed_bridges:
            return
        if await self._cog.bot.cog_disabled_in_guild(self._cog, message.guild):
            return
        if not self._cog.is_message_allowed(self.message):
            return

        webhook, thread = await self._cog.get_webhook(message.channel.id)
        if webhook is None:
            return

        content: Optional[str] = message.content
        if content is None and not message.attachments:
            return
        files = await Tunnel.files_from_attach(message)

        embeds: List[discord.Embed] = []
        if content and len(content) > 2000:
            embeds.append(discord.Embed(description=content))
            content = None

        extra_embed = discord.Embed()
        extra_embed.description = ""
        if len(files) != len(message.attachments):
            extra_embed.description += (
                "Some of the attachments could not be forwarded,"
                " probably due to their size."
            )
        latency = datetime.datetime.now(tz=datetime.timezone.utc) - message.created_at
        if latency.seconds > 15:
            extra_embed.set_footer(text="Delayed!")
            extra_embed.timestamp = message.created_at

        if extra_embed:
            embeds.append(extra_embed)

        source = "Discord" if IS_DISCORD else "Fluxer"
        username = f"{message.author.display_name} [relayed from {source}]"
        token = async_context.set(WebhookAdapter(webhook.red_webhook_base_url))
        try:
            remote_message = await webhook.send(
                message.content,
                files=files,
                thread=thread,
                username=username,
                avatar_url=str(message.author.avatar or ""),
                embeds=embeds,
                wait=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        finally:
            async_context.reset(token)
        await self._cog.config.custom(MESSAGES, message.id).set(
            {
                "message_id": remote_message.id,
                "user_id": message.author.id,
            }
        )
        await self._cog.config.custom(
            USER_MESSAGES, message.author.id, message.id
        ).remote_message_id.set(remote_message.id)


class MessageEdit(MessageEvent):
    def __init__(self, cog: FluxerBridge, /, *, message: discord.Message) -> None:
        super().__init__(cog)
        self.message = message
        self._cfg_msg = self._cog.config.custom(MESSAGES, self.message.id)
        self.remote_message_id: Optional[int] = None
        self.user_id: Optional[int] = None

    async def _init(self) -> None:
        message_data = await self._cfg_msg.all()
        self.remote_message_id = message_data["message_id"]
        self.user_id = message_data["user_id"]

    async def execute(self) -> None:
        if self.remote_message_id is None:
            return
        if self.message.channel.id in self._cog.removed_bridges:
            return
        if not self._cog.is_message_allowed(self.message):
            return
        message = self.message
        if message.guild is None or await self._cog.bot.cog_disabled_in_guild(
            self._cog, message.guild
        ):
            return

        webhook, thread = await self._cog.get_webhook(self.message.channel.id)
        if webhook is None:
            return

        content: Optional[str] = message.content
        embeds: List[discord.Embed] = []
        if content and len(content) > 2000:
            embeds.append(discord.Embed(description=content))
            embeds.append(
                discord.Embed(description=discord.utils.format_dt(message.created_at))
            )
            content = None

        now = datetime.datetime.now(tz=datetime.timezone.utc)
        latency = now - (message.edited_at or now)
        if latency.seconds > 15:
            embeds.append(
                discord.Embed(
                    description=(
                        f"{discord.utils.format_dt(message.created_at)}\n"
                        "Edit delayed!"
                        f" {discord.utils.format_dt(message.edited_at or now)}"
                    )
                )
            )

        if not embeds:
            embeds = discord.utils.MISSING

        token = async_context.set(WebhookAdapter(webhook.red_webhook_base_url))
        try:
            await webhook.edit_message(
                self.remote_message_id,
                content=content,
                embeds=embeds,
                thread=thread,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        finally:
            async_context.reset(token)


class MessageDelete(MessageEvent):
    def __init__(
        self,
        cog: FluxerBridge,
        /,
        *,
        guild_id: int,
        channel_id: int,
        message_id: int,
    ) -> None:
        super().__init__(cog)
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.message_id = message_id
        self._cfg_msg = self._cog.config.custom(MESSAGES, self.message_id)
        self.remote_message_id: Optional[int] = None
        self.user_id: Optional[int] = None

    async def _init(self) -> None:
        message_data = await self._cfg_msg.all()
        self.remote_message_id = message_data["message_id"]
        self.user_id = message_data["user_id"]

    async def execute(self) -> None:
        if self.channel_id in self._cog.removed_bridges:
            return
        if self.remote_message_id is None:
            return
        if await self._cog.bot.cog_disabled_in_guild_raw(
            self._cog.qualified_name, self.guild_id
        ):
            return

        webhook, thread = await self._cog.get_webhook(self.channel_id)
        if webhook is None:
            return

        token = async_context.set(WebhookAdapter(webhook.red_webhook_base_url))
        try:
            await webhook.delete_message(self.remote_message_id, thread=thread)
        finally:
            async_context.reset(token)
        await self._cfg_msg.clear()
        await self._cog.config.custom(
            USER_MESSAGES, self.user_id, self.message_id
        ).clear()


class FluxerBridge(commands.Cog):
    """Fluxer <-> Discord bridge relaying messages with webhooks."""

    def __init__(self, bot: Red) -> None:
        super().__init__()
        self.bot = bot
        self._session: aiohttp.ClientSession
        self.config = Config.get_conf(
            self,
            176070082584248320,
            force_registration=True,
        )
        self.config.register_global(
            bots_allowed=False, bots_allowlist=[], bots_blocklist=[]
        )
        self.config.register_channel(webhook_data=None)
        # user id -> "local" message id -> {...}
        self.config.init_custom(USER_MESSAGES, 2)
        self.config.register_custom(USER_MESSAGES, remote_message_id=True)
        # "local" message id -> {...}
        self.config.init_custom(MESSAGES, 1)
        self.config.register_custom(MESSAGES, message_id=None, user_id=None)
        self._queue: asyncio.Queue[MessageEvent] = asyncio.Queue()
        self._queue_handler: Optional[asyncio.Task[None]] = None
        self.removed_bridges: Set[int] = set()
        # bot allow configuration
        self.bots_allowed = False
        self.bots_allowlist = set()
        self.bots_blocklist = set()

    async def initialize(self) -> None:
        self._session = aiohttp.ClientSession()
        self._queue_handler = asyncio.create_task(self._handle_queue())
        self.bots_allowlist = set(await self.config.bots_allowlist())
        self.bots_blocklist = set(await self.config.bots_blocklist())
        self.bots_allowed = await self.config.bots_allowed()

    async def cog_unload(self) -> None:
        if self._queue_handler is not None:
            self._queue_handler.cancel()
            try:
                await self._queue_handler
            except asyncio.CancelledError:
                pass
        await self._session.close()

    async def _handle_queue(self) -> None:
        while True:
            try:
                event = await self._queue.get()
                await self._handle_queue_item(event)
            except Exception as exc:
                log.error(
                    "Unexpected error occurred while working on the queue.",
                    exc_info=exc,
                )

    async def _handle_queue_item(self, event: MessageEvent) -> None:
        try:
            await event.init()
        except Exception as exc:
            log.error(
                "Unexpected error occurred while initializing work on a queue item."
                " Will not retry.",
                exc_info=exc,
            )
            event.finished.set()
            return
        attempt = 0
        while True:
            if IS_DISCORD:
                # be aggressive on Fluxer early due to its instability and retry forever
                if attempt < 4:
                    delay = random.random()
                else:
                    delay = 2.0 ** ((attempt - 3) % 8)
                retry_on_fail = True
            else:
                delay = random.random() + 2.0 * attempt
                retry_on_fail = attempt >= 9

            log_suffix = (
                f"Retrying in {delay:.2f}s." if retry_on_fail else "Will not retry."
            )
            try:
                await event.execute()
            except aiohttp.ClientError as exc:
                log.warning(
                    "aiohttp error occurred, while working on a queue item. %s",
                    log_suffix,
                    exc_info=exc,
                )
            except discord.HTTPException as exc:
                if exc.status >= 500:
                    log.warning(
                        "Received server error, while working on a queue item. %s",
                        log_suffix,
                        exc_info=exc,
                    )
                elif 400 <= exc.status < 500:
                    log.error(
                        "Received client error, while working on a queue item."
                        " Will not retry.",
                        exc_info=exc,
                    )
                    break
                else:
                    log.warning(
                        "Unexpected HTTP error occurred, while working on a queue item."
                        " %s",
                        log_suffix,
                        exc_info=exc,
                    )
            except Exception as exc:
                log.error(
                    "Unexpected error occurred, while working on a queue item."
                    " Will not retry.",
                    exc_info=exc,
                )
                break
            else:
                event.success = True
                break

            if retry_on_fail:
                break
            await asyncio.sleep(delay)
            attempt += 1

        event.finished.set()

    def is_message_allowed(self, message: discord.Message) -> bool:
        if not message.author.bot:
            return True
        if not self.bots_allowed:
            return False
        if self.bots_allowlist and message.author.id not in self.bots_allowlist:
            return False
        if message.author.id in self.bots_blocklist:
            return False
        if message.webhook_id is not None and message.application_id is None:
            return False
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        self._queue.put_nowait(MessageCreate(self, message=message))

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if IS_DISCORD or payload.guild_id is None:
            return
        self._queue.put_nowait(MessageEdit(self, message=payload.message))

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(
        self, payload: discord.RawBulkMessageDeleteEvent
    ) -> None:
        if IS_DISCORD or payload.guild_id is None:
            return
        for message_id in payload.message_ids:
            self._queue.put_nowait(
                MessageDelete(
                    self,
                    guild_id=payload.guild_id,
                    channel_id=payload.channel_id,
                    message_id=message_id,
                )
            )

    @commands.Cog.listener()
    async def on_raw_message_delete(
        self, payload: discord.RawMessageDeleteEvent
    ) -> None:
        if IS_DISCORD or payload.guild_id is None:
            return
        self._queue.put_nowait(
            MessageDelete(
                self,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
            )
        )

    async def get_webhook(
        self, channel_id: int
    ) -> Tuple[Optional[Webhook], discord.abc.Snowflake]:
        webhook_data = await self.config.channel_from_id(channel_id).webhook_data()
        if not webhook_data:
            return None, discord.utils.MISSING

        return self.get_webhook_from_data(webhook_data)

    def get_webhook_from_data(
        self, webhook_data: Dict[str, Any]
    ) -> Tuple[Webhook, discord.abc.Snowflake]:
        webhook_data["type"] = 1
        webhook_base_url = webhook_data.pop("red_webhook_base_url")
        thread_id = webhook_data.pop("red_thread_id")
        webhook = Webhook(webhook_data, self._session)  # type: ignore[arg-type]
        webhook.red_webhook_base_url = webhook_base_url
        thread = discord.Object(thread_id) if thread_id else discord.utils.MISSING
        return webhook, thread

    @commands.guildowner()
    @commands.guild_only()
    @commands.group()
    async def fluxerbridge(self, ctx: commands.GuildContext) -> None:
        """
        Fluxer bridge settings.

        To setup a one-way bridge, you need to use `[p]fluxerbridge add`
        with a webhook URL for the other platform.
        Do the same on the other platform for a two-way bridge.
        """

    @fluxerbridge.command(name="add", aliases=["create"])
    async def fluxerbridge_add(self, ctx: commands.GuildContext) -> None:
        """
        Add a new one-way bridge for the current channel.

        This will make the bot listen in the current channel
        and send them over the provided webhook URL.
        """
        if await self.config.channel(ctx.channel).webhook_data():
            await ctx.send("A bridge is already set in this channel!")

        try:
            dm_msg = await ctx.author.send("Send webhook URL in the next message.")
        except discord.Forbidden:
            await ctx.send("I couldn't send you a DM.")
            return

        msg = await self.bot.wait_for(
            "message", check=MessagePredicate.same_context(channel=dm_msg.channel)
        )
        match = WEBHOOK_URL_RE.match(msg.content)
        if match is None:
            await ctx.author.send(
                "The content of your message is not a valid webhook URL."
            )
            return

        webhook_base_url = match["base_url"]
        if webhook_base_url not in VALID_BASE_URLS:
            if IS_DISCORD:
                await ctx.author.send(
                    "The given URL is not a Fluxer webhook."
                    " Note that self-hosted Fluxer instances"
                    " are not currently supported."
                )
            else:
                await ctx.author.send("The given URL is not a Discord webhook.")
            return

        try:
            url = yarl.URL(msg.content)
        except ValueError:
            await ctx.author.send("This does not appear to be a valid URL.")
            return

        thread_id = url.query.get("thread_id")
        webhook_id = match["id"]
        webhook_token = match["token"]
        webhook_data = {
            "red_webhook_base_url": webhook_base_url,
            "id": webhook_id,
            "token": webhook_token,
            "red_thread_id": thread_id,
        }

        event = WebhookTestMessageEvent(self, webhook_data=webhook_data.copy())
        self._queue.put_nowait(event)
        await event.finished.wait()

        if not event.success:
            if isinstance(event.last_error, discord.HTTPException):
                await ctx.author.send(
                    "Failed to send a message through provided webhook URL,"
                    f" received: {event.last_error.status}"
                    f" (error code: {event.last_error.code})"
                )
                return

            await ctx.author.send(
                "Failed to send a message through provided webhook URL."
            )
            return

        await self.config.channel(ctx.channel).webhook_data.set(webhook_data)

        await ctx.author.send("A one-way bridge has been set up.")
        await ctx.send("A one-way bridge has been set up.")

    @fluxerbridge.command(name="remove", aliases=["delete"])
    async def fluxerbridge_remove(self, ctx: commands.GuildContext) -> None:
        """Remove a one-way bridge for the current channel."""
        if not await self.config.channel(ctx.channel).webhook_data():
            await ctx.send("There is no bridge in this channel!")

        await self.config.channel(ctx.channel).clear()
        self.removed_bridges.add(ctx.channel.id)
        await ctx.send("Bridge removed.")

    @commands.is_owner()
    @fluxerbridge.command(name="fulllist")
    async def fluxerbridge_fulllist(self, ctx: commands.GuildContext) -> None:
        """List bridges from all servers."""
        lines: List[str] = []
        for channel_id, channel_data in await self.config.all_channels():
            webhook_data = channel_data["webhook_data"]
            if webhook_data:
                lines.append(
                    f"- <#{channel_id}> - Webhook {webhook_data['id']}"
                    f" at {webhook_data['red_webhook_base_url']}"
                )

        content = "\n".join(lines)
        for page in pagify(content):
            await ctx.send(page)

    @fluxerbridge.command(name="list")
    async def fluxerbridge_list(self, ctx: commands.GuildContext) -> None:
        """List bridges in the current server."""
        lines: List[str] = []
        for channel in itertools.chain(ctx.guild.channels, ctx.guild.threads):
            webhook_data = await self.config.channel(channel).webhook_data()
            if webhook_data:
                lines.append(
                    f"- {channel.mention} - Webhook {webhook_data['id']}"
                    f" at {webhook_data['red_webhook_base_url']}"
                )

        content = "\n".join(lines)
        for page in pagify(content):
            await ctx.send(page)

    @commands.is_owner()
    @fluxerbridge.group(name="bots")
    async def fluxerbridge_bots(self, ctx: commands.GuildContext) -> None:
        """
        Bot-wide configuration for relaying bot messages.

        Use `[p]fluxerbridge bots allowlist` commands to configure the bot allowlist
        and then use `[p]fluxerbridge bots allow` to allow messages of those bots
        to be relayed.

        Alternatively, use `[p]fluxerbridge bots blocklist` commands to configure
        a bot blocklist.

        If the bot messages are allowed to be relayed and the allowlist is empty,
        messages of all bots excluding ones on the blocklist will be relayed.

        Non-application webhook messages are ignored regardless.
        """

    @fluxerbridge_bots.command(name="allow")
    async def fluxerbridge_bots_allow(self, ctx: commands.GuildContext) -> None:
        """
        Allow bot messages to be relayed (bot-wide setting).

        Make sure to use `[p]fluxerbridge bots allowlist` commands to
        configure bot allowlist *before* running this command, if you want to
        limit the bots whose messages can be relayed.
        """
        await self.config.bots_allowed.set(True)
        self.bots_allowed = True
        await ctx.send(
            "Bot messages are now relayed on all bridges configured on the bot."
        )

    @fluxerbridge_bots.command(name="disallow")
    async def fluxerbridge_bots_disallow(self, ctx: commands.GuildContext) -> None:
        """
        Disallow bot messages from being relayed (bot-wide setting).

        Make sure to use `[p]fluxerbridge bots allowlist` commands to
        configure bot allowlist *before* running this command, if you want to
        limit the bots whose messages can be relayed.
        """
        await self.config.bots_allowed.set(False)
        self.bots_allowed = False
        await ctx.send(
            "Bot messages are no longer relayed on all bridges configured on the bot."
        )

    @fluxerbridge_bots.group(name="allowlist")
    async def fluxerbridge_bots_allowlist(self, ctx: commands.GuildContext) -> None:
        """
        Configure which bots can have their messages relayed (bot-wide setting).

        If the bot messages are allowed to be relayed and the allowlist is empty,
        messages of all bots excluding ones on the blocklist will be relayed.

        Note that if the allowlist is not empty, it takes precedence over the blocklist.

        Non-application webhook messages are ignored regardless.
        """

    @fluxerbridge_bots_allowlist.command(name="add")
    async def fluxerbridge_bots_allowlist_add(
        self, ctx: commands.GuildContext, user: discord.User
    ) -> None:
        """Add a bot to the allowlist (bot-wide setting)."""
        if not user.bot:
            await ctx.send("This user is not a bot!")
            return
        if user.id in self.bots_allowlist:
            await ctx.send("This user is already on the allowlist!")
            return
        async with self.config.bots_allowlist() as bots_allowlist:
            bots_allowlist.append(user.id)
        self.bots_allowlist.add(user.id)
        await ctx.send("The user has been added to the allowlist.")

    @fluxerbridge_bots_allowlist.command(name="remove", aliases=["delete"])
    async def fluxerbridge_bots_allowlist_remove(
        self, ctx: commands.GuildContext, user: discord.User
    ) -> None:
        """Remove a bot from the allowlist (bot-wide setting)."""
        if not user.bot:
            await ctx.send("This user is not a bot!")
            return
        if user.id not in self.bots_allowlist:
            await ctx.send("This user is already not on the allowlist!")
            return
        if len(self.bots_allowlist) == 1:
            await self.config.bots_allowed.set(False)
            self.bots_allowed = False
        async with self.config.bots_allowlist() as bots_allowlist:
            bots_allowlist.remove(user.id)
        self.bots_allowlist.remove(user.id)
        if self.bots_allowlist:
            await ctx.send("The user has been removed from the allowlist.")
        else:
            command = inline(f"{ctx.prefix}fluxerbridge bots allow")
            await ctx.send(
                "The bot has been removed from the allowlist and the list is now empty."
                f" To avoid mistakes, you'll need to run {command} again,"
                " if you really want to allow all bots to have their messages relayed."
            )

    @fluxerbridge_bots_allowlist.command(name="clear")
    async def fluxerbridge_bots_allowlist_clear(
        self, ctx: commands.GuildContext
    ) -> None:
        """Clear the allowlist (bot-wide setting)."""
        await self.config.bots_allowed.set(False)
        self.bots_allowed = False
        await self.config.bots_allowlist.clear()
        self.bots_allowlist.clear()
        command = inline(f"{ctx.prefix}fluxerbridge bots allow")
        await ctx.send(
            "The bots allowlist has been cleared."
            f" To avoid mistakes, you'll need to run {command} again,"
            " if you really want to allow all bots to have their messages relayed."
        )

    @fluxerbridge_bots.group(name="blocklist")
    async def fluxerbridge_bots_blocklist(self, ctx: commands.GuildContext) -> None:
        """
        Configure which bots cannot have their messages relayed (bot-wide setting).

        Note that if the bot messages are allowed to be relayed and the allowlist
        is not empty, it will take precedence over this list.

        Non-application webhook messages are ignored regardless.
        """

    @fluxerbridge_bots_blocklist.command(name="add")
    async def fluxerbridge_bots_blocklist_add(
        self, ctx: commands.GuildContext, user: discord.User
    ) -> None:
        """Add a bot to the blocklist (bot-wide setting)."""
        if not user.bot:
            await ctx.send("This user is not a bot!")
            return
        if user.id in self.bots_blocklist:
            await ctx.send("This user is already on the blocklist!")
            return
        async with self.config.bots_blocklist() as bots_blocklist:
            bots_blocklist.append(user.id)
        self.bots_blocklist.add(user.id)
        await ctx.send("The user has been added to the blocklist.")

    @fluxerbridge_bots_blocklist.command(name="remove", aliases=["delete"])
    async def fluxerbridge_bots_blocklist_remove(
        self, ctx: commands.GuildContext, user: discord.User
    ) -> None:
        """Remove a bot from the blocklist (bot-wide setting)."""
        if not user.bot:
            await ctx.send("This user is not a bot!")
            return
        if user.id not in self.bots_blocklist:
            await ctx.send("This user is already not on the blocklist!")
            return
        async with self.config.bots_blocklist() as bots_blocklist:
            bots_blocklist.remove(user.id)
        self.bots_blocklist.remove(user.id)
        if self.bots_blocklist:
            await ctx.send("The user has been removed from the blocklist.")
        else:
            await ctx.send(
                "The bot has been removed from the blocklist and the list is now empty."
            )

    @fluxerbridge_bots_blocklist.command(name="clear")
    async def fluxerbridge_bots_blocklist_clear(
        self, ctx: commands.GuildContext
    ) -> None:
        """Clear the blocklist (bot-wide setting)."""
        await self.config.bots_blocklist.clear()
        self.bots_blocklist.clear()
        await ctx.send("The bots blocklist has been cleared.")
