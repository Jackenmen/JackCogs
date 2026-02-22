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
from typing import List, Optional, Set, Tuple

import aiohttp
import discord
import yarl
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.config import Config
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils.predicates import MessagePredicate

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


class Webhook(discord.Webhook):
    __slots__ = ("red_webhook_base_url",)

    @property
    def url(self) -> str:
        """:class:`str` : Returns the webhook's url."""
        return f"https://{self.red_webhook_base_url}/webhooks/{self.id}/{self.token}"


class MessageEvent:
    def __init__(self, cog: FluxerBridge, /) -> None:
        self._cog = cog
        self._initialized = False

    async def init(self) -> None:
        if not self._initialized:
            await self._init()

    async def _init(self) -> None:
        pass

    async def execute(self) -> None:
        raise NotImplementedError(
            f"execute() method for {self.__class__} has not been implemented"
        )


class MessageCreate(MessageEvent):
    def __init__(self, cog: FluxerBridge, /, *, message: discord.Message) -> None:
        super().__init__(cog)
        self.message = message

    async def execute(self) -> None:
        if self.message.channel.id in self._cog.removed_bridges:
            return
        message = self.message
        if await self._cog.bot.cog_disabled_in_guild(self._cog, message.guild):
            return

        webhook, thread = await self._cog.get_webhook(message.channel.id)
        if webhook is None:
            return

        content = message.content
        embeds: List[discord.Embed] = []
        if len(content) > 2000:
            embeds.append(discord.Embed(description=content))
            content = None

        latency = datetime.datetime.now(tz=datetime.timezone.utc) - message.created_at
        if latency.seconds > 15:
            embeds.append(
                discord.Embed(
                    description=(
                        f"Delayed! {discord.utils.format_dt(message.created_at)}"
                    )
                )
            )

        remote_message = await webhook.send(
            message.content,
            thread=thread,
            username=message.author.display_name,
            avatar_url=message.author.avatar.url,
            embeds=embeds,
        )
        await self._cog.config.custom(MESSAGES, message.id).set(
            {
                "message_id": remote_message.id,
                "user_id": message.author.id,
            }
        )
        await self._cog.config.custom(MESSAGES, message.author.id, message.id).ack.set(
            True
        )


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
        message = self.message
        if message.guild is None or await self._cog.bot.cog_disabled_in_guild(
            self._cog, message.guild
        ):
            return

        webhook, thread = await self._cog.get_webhook(self.message.channel.id)
        if webhook is None:
            return

        content = message.content
        embeds: List[discord.Embed] = []
        if len(content) > 2000:
            embeds.append(discord.Embed(description=content))
            embeds.append(
                discord.Embed(description=discord.utils.format_dt(message.created_at))
            )
            content = None

        latency = datetime.datetime.now(tz=datetime.timezone.utc) - message.edited_at
        if latency.seconds > 15:
            embeds.append(
                discord.Embed(
                    description=(
                        f"{discord.utils.format_dt(message.created_at)}\n"
                        f"Edit delayed! {discord.utils.format_dt(message.edited_at)}"
                    )
                )
            )

        if not embeds:
            embeds = discord.utils.MISSING

        await webhook.edit_message(
            self.remote_message_id,
            content=content,
            embeds=embeds,
            thread=thread,
        )


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

        await webhook.delete_message(self.remote_message_id, thread=thread)
        await self._cfg_msg.clear()
        await self._cog.config.custom(USER_MESSAGES, self.user_id, self.message_id)


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
        self.config.register_channel(webhook_data=None)
        # user id -> "local" message id -> {...}
        self.config.init_custom(USER_MESSAGES, 2)
        self.config.register_custom(USER_MESSAGES, remote_message_id=True)
        # "local" message id -> {...}
        self.config.init_custom(MESSAGES, 1)
        self.config.register_custom(MESSAGES, message_id=None, user_id=None)
        self._queue = asyncio.Queue()
        self._queue_handler: Optional[asyncio.Task] = None
        self.removed_bridges: Set[int] = set()

    async def initialize(self) -> None:
        self._session = aiohttp.ClientSession()
        self._queue_handler = asyncio.create_task(self._handle_queue())

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
            return
        for attempt in range(10):
            delay = random.random() + (0.0 if attempt < 4 else 2.0 * (attempt - 3))
            log_suffix = (
                f"Retrying in {delay:.2f}s." if attempt < 9 else "Will not retry."
            )
            try:
                await event.execute()
            except aiohttp.ClientError as exc:
                log.warning(
                    "Server error occurred, while working on a queue item. %s",
                    log_suffix,
                    exc_info=exc,
                )
                continue
            except discord.HTTPException as exc:
                if exc.code >= 500:
                    log.warning(
                        "Server error occurred, while working on a queue item. %s",
                        log_suffix,
                    )
                elif 400 <= exc.code < 500:
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
                # success!
                break
            if attempt < 9:
                await asyncio.sleep(delay)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        self._queue.put_nowait(MessageCreate(self, message=message))

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if not IS_DISCORD or payload.guild_id is None:
            return
        self._queue.put_nowait(MessageEdit(self, message=payload.message))

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(
        self, payload: discord.RawBulkMessageDeleteEvent
    ) -> None:
        if not IS_DISCORD or payload.guild_id is None:
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
        if not IS_DISCORD or payload.guild_id is None:
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
    ) -> Tuple[Optional[discord.Webhook], discord.abc.Snowflake]:
        webhook_data = await self.config.channel_from_id(channel_id).webhook_data()
        if not webhook_data:
            return None, discord.utils.MISSING

        webhook_data["type"] = 1
        webhook_base_url = webhook_data.pop("red_webhook_base_url")
        thread_id = webhook_data.pop("red_thread_id")
        webhook = Webhook(webhook_data, self._session)
        webhook.red_webhook_base_url = webhook_base_url
        thread = discord.Object(thread_id) if thread_id else discord.utils.MISSING
        return webhook, thread

    @commands.guildowner()
    @commands.guild_only()
    @commands.group()
    async def fluxerbridge(self, ctx: commands.Context) -> None:
        """
        Fluxer bridge settings.

        To setup a one-way bridge, you need to use `[p]fluxerbridge add`
        with a webhook URL for the other platform.
        Do the same on the other platform for a two-way bridge.
        """

    @fluxerbridge.command(name="add", aliases=["create"])
    async def fluxerbridge_add(self, ctx: commands.Context) -> None:
        """
        Add a new one-way bridge for the current channel.

        This will make the bot listen in the current channel
        and send them over the provided webhook URL.
        """
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
        await self.config.channel(ctx.channel).webhook_data.set(
            {
                "red_webhook_base_url": webhook_base_url,
                "id": webhook_id,
                "token": webhook_token,
                "red_thread_id": thread_id,
            }
        )
        await ctx.author.send("A one-way bridge has been set up.")
        await ctx.send("A one-way bridge has been set up.")

    @fluxerbridge.command(name="remove", aliases=["delete"])
    async def fluxerbridge_remove(self, ctx: commands.Context) -> None:
        """Remove a one-way bridge for the current channel."""
        if not await self.config.channel(ctx.channel).webhook_data():
            await ctx.send("There is no bridge in this channel!")

        await self.config.channel(ctx.channel).clear()
        self.removed_bridges.add(ctx.channel.id)
        await ctx.send("Bridge removed.")

    @commands.is_owner()
    @fluxerbridge.command(name="fulllist")
    async def fluxerbridge_fulllist(self, ctx: commands.Context) -> None:
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
    async def fluxerbridge_list(self, ctx: commands.Context) -> None:
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
