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
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    Iterable,
    List,
    Match,
    Set,
    Tuple,
    TypeVar,
    Union,
    overload,
)

import aiohttp
import discord
import yarl

# DEP-WARN
from discord.http import HTTPClient, Route
from discord.webhook.async_ import AsyncWebhookAdapter, async_context
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands import NoParseOptional as Optional
from redbot.core.config import Config
from redbot.core.utils.chat_formatting import inline, pagify
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate
from redbot.core.utils.tunnel import Tunnel
from typing_extensions import Self

IS_DISCORD = discord.utils.oauth_url("").startswith("https://discord.com/")
USER_MESSAGES = "USER_MESSAGES"
MESSAGES = "MESSAGES"
EMOJI_CACHE = "EMOJI_CACHE"
WEBHOOK_URL_RE = re.compile(
    r"https://(?P<base_url>.+)/webhooks"
    r"/(?P<id>[0-9]{17,20})/(?P<token>[A-Za-z0-9\.\-\_]{60,})"
)
VALID_API_HOSTNAMES = ("api.fluxer.app",) if IS_DISCORD else ("discord.com",)
VALID_BASE_URLS = (
    ("api.fluxer.app",) if IS_DISCORD else ("discord.com/api", "discordapp.com/api")
)
LOTTIE_PLACEHOLDER_URL = "https://cdn.discordapp.com/stickers/1475357345885196308.png"
# DEP-WARN
MAX_FILE_SIZE = discord.utils.DEFAULT_FILE_SIZE_LIMIT_BYTES
MENTIONS_RE = re.compile(r"<(?P<mention_type>@[&!]?|#)(?P<id>[0-9]{15,20})>")
EMOJI_RE = re.compile(r"<a?:[a-zA-Z0-9\_]{1,32}:([0-9]{15,20})>")
T = TypeVar("T")

log = logging.getLogger("red.jackcogs.fluxerbridge")


class FluxerMaintenanceError(Exception):
    """Raised by the retry logic to indicate downtime."""


class WebhookAdapter(AsyncWebhookAdapter):
    def __init__(self, base: str) -> None:
        super().__init__()
        self.__base = base

    async def request(  # type: ignore[no-untyped-def]
        self, route, *args: Any, **kwargs: Any
    ) -> Any:
        route.url = f"https://{self.__base}" + route.url[len(route.BASE) :]

        # handle Fluxer differences
        data = await super().request(route, *args, **kwargs)
        timestamp = data.get("edited_timestamp")
        if timestamp is not None:
            data["edited_timestamp"] = timestamp.replace("Z", "+00:00")
        for raw_embed in data.get("embeds", []):
            timestamp = raw_embed.get("timestamp")
            if timestamp is not None:
                raw_embed["timestamp"] = timestamp.replace("Z", "+00:00")

        return data


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

    @property
    def _last_webhook(self) -> Optional[Webhook]:
        try:
            return self.__last_webhook
        except AttributeError:
            return None

    @_last_webhook.setter
    def _last_webhook(self, value: Webhook) -> None:
        self.__last_webhook = value

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


class MessageParams:
    def __init__(
        self,
        cog: FluxerBridge,
        webhook: Webhook,
        thread: discord.abc.Snowflake = discord.utils.MISSING,
        *,
        content: str,
        files: List[discord.File],
        embeds: List[discord.Embed],
    ) -> None:
        self._cog = cog
        self.webhook = webhook
        self.thread = thread
        self.content = content
        self.files = files
        self.embeds = embeds

    @classmethod
    def _mention_replacer(cls, guild: discord.Guild) -> Callable[[Match[str]], str]:
        def replace_mention(match: Match[str]) -> str:
            mention_type = match["mention_type"]
            object_id = int(match["id"])
            if mention_type == "@&":
                if role := guild.get_role(object_id):
                    return f"@{role.name}"
            elif mention_type == "#":
                if channel := guild.get_channel(object_id):
                    return f"#{channel.name}"
            else:
                if member := guild.get_member(object_id):
                    return f"@{member.display_name}"
            return match.group()

        return replace_mention

    @staticmethod
    def _extract_partial_emojis(
        bot: Red, content: str
    ) -> Iterable[discord.PartialEmoji]:
        for match in EMOJI_RE.finditer(content):
            emoji = discord.PartialEmoji.from_str(match.group())
            # DEP-WARN
            emoji._state = bot._connection
            print(emoji)
            yield emoji

    @classmethod
    async def from_message(
        cls,
        event: MessageEvent,
        message: discord.Message,
        *,
        remote_message_id: Optional[int] = None,
    ) -> Optional[MessageParams]:
        cog = event._cog
        if message.channel.id in cog.removed_bridges:
            return None
        if not cog.is_message_allowed(message):
            return None
        guild = message.guild
        if guild is None or await cog.bot.cog_disabled_in_guild(cog, guild):
            return None

        webhook, thread = await cog.get_webhook(message.channel.id)
        event._last_webhook = webhook
        if webhook is None:
            return None

        content: str = message.content or ""
        sticker_urls = [
            (
                sticker.url
                if sticker.format is not discord.StickerFormatType.lottie
                else LOTTIE_PLACEHOLDER_URL
            ).replace("cdn.discordapp.com", "media.discordapp.net")
            + "?size=160"
            for sticker in message.stickers
        ]
        msg_embeds = [embed for embed in message.embeds if embed.type == "rich"]
        if (
            not content
            and (remote_message_id is not None or not message.attachments)
            and not sticker_urls
            and not msg_embeds
        ):
            return None
        files = (
            await Tunnel.files_from_attach(message)
            if remote_message_id is None
            else discord.utils.MISSING
        )
        embeds: List[discord.Embed] = []

        emoji_cache = cog.emoji_cache.get_from_base_url(webhook.red_webhook_base_url)
        if emoji_cache is not None:
            emoji_replacements, _ = await emoji_cache.get_emoji_replacements(
                cls._extract_partial_emojis(cog.bot, content)
            )
            content = EMOJI_RE.sub(
                lambda m: emoji_replacements.get(m.group(0), m.group(0)),
                content,
            )

        # maybe this could be applied to embeds in the future as well
        content = MENTIONS_RE.sub(cls._mention_replacer(guild), content)
        content_length = len(content)
        max_length = 2000
        if content_length > max_length:
            embeds.append(discord.Embed(description=content))
            if sticker_urls:
                # rest of the stickers get lost
                # but the client does not let you send multiple anyway
                embeds[0] = embeds[0].set_image(url=sticker_urls[0])
            content = ""
        elif sticker_urls:
            sticker_text = "\n".join(sticker_urls)
            if content_length + len(sticker_text) + 1 > max_length:
                embeds.append(discord.Embed().set_image(url=sticker_urls[0]))
                if IS_DISCORD:
                    # Fluxer does not render image-only embeds for some reason
                    embeds[0].description = "\u200b"
            else:
                content = f"{content}\n{sticker_text}"

        had_more_embeds = False
        for embed in msg_embeds:
            if len(embeds) == 10:
                had_more_embeds = True
                break
            embeds.append(embed)

        extra_embed = discord.Embed()
        extra_embed.description = ""
        if sum(a.size for a in message.attachments) > MAX_FILE_SIZE:
            extra_embed.description += (
                "The attachments could not be forwarded due to their size."
            )
        elif remote_message_id is None and len(files) != len(message.attachments):
            extra_embed.description += "Some of the attachments could not be forwarded."

        remote_created_at = (
            datetime.datetime.now(tz=datetime.timezone.utc)
            if remote_message_id is None
            else discord.Object(remote_message_id).created_at
        )
        latency = remote_created_at - message.created_at
        if latency.seconds > 15:
            extra_embed.set_footer(text="Delayed!")
            extra_embed.timestamp = message.created_at

        add_edit_delay = False
        edit_latency = datetime.timedelta()
        if message.edited_at is not None:
            now = datetime.datetime.now(tz=datetime.timezone.utc)
            edit_latency = now - message.edited_at
            if edit_latency.seconds > 15:
                add_edit_delay = True

        if had_more_embeds or ((extra_embed or add_edit_delay) and len(embeds) == 10):
            extra_embed.description += (
                "\nSome of the embeds could not be forwarded due to"
                " exceeding max number of embeds (10)."
            )

        if add_edit_delay:
            assert message.edited_at is not None, "mypy"
            extra_embed.description += (
                f"\n\n*Edit delayed! {discord.utils.format_dt(message.edited_at)}*"
            )

        if extra_embed:
            if len(embeds) == 10:
                embeds.pop()
            embeds.append(extra_embed)

        if not embeds:
            embeds = discord.utils.MISSING

        return MessageParams(
            cog,
            webhook,
            thread,
            content=content,
            files=files,
            embeds=embeds,
        )


class MessageCreate(MessageEvent):
    def __init__(self, cog: FluxerBridge, /, *, message: discord.Message) -> None:
        super().__init__(cog)
        self.message = message

    async def execute(self) -> None:
        message = self.message
        msg_params = await MessageParams.from_message(self, message)
        if msg_params is None:
            return

        source = "Discord" if IS_DISCORD else "Fluxer"
        bot_indicator = (
            "\N{ROBOT FACE}" if message.author.bot else "\N{BUST IN SILHOUETTE}"
        )
        username = (
            f"{bot_indicator} {message.author.display_name} [relayed from {source}]"
        )
        token = async_context.set(
            WebhookAdapter(msg_params.webhook.red_webhook_base_url)
        )
        try:
            remote_message = await msg_params.webhook.send(
                msg_params.content,
                embeds=msg_params.embeds,
                files=msg_params.files,
                thread=msg_params.thread,
                username=username,
                avatar_url=str(message.author.avatar or ""),
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
        self.remote_message_id = remote_message_id = message_data["message_id"]
        self.user_id = message_data["user_id"]
        self.remote_created_at = discord.Object(remote_message_id).created_at

    async def execute(self) -> None:
        if self.remote_message_id is None:
            return

        msg_params = await MessageParams.from_message(
            self, self.message, remote_message_id=self.remote_message_id
        )
        if msg_params is None:
            return

        token = async_context.set(
            WebhookAdapter(msg_params.webhook.red_webhook_base_url)
        )
        try:
            await msg_params.webhook.edit_message(
                self.remote_message_id,
                content=msg_params.content,
                embeds=msg_params.embeds,
                thread=msg_params.thread,
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
        self._last_webhook = webhook
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


class InstanceEmojiCache:
    MAX_EMOJIS = 50

    def __init__(
        self,
        global_cache: EmojiCache,
        hostname: str,
        *,
        guild_id: int,
        token: str,
        static_cache: Optional[Dict[int, str]] = None,
        animated_cache: Optional[Dict[int, str]] = None,
    ) -> None:
        self.global_cache = global_cache
        self._cog = global_cache._cog
        self.hostname = hostname
        self.guild_id = guild_id
        self._token = token
        self._static_cache = static_cache or {}
        self._animated_cache = animated_cache or {}
        # DEP-WARN
        self._http = HTTPClient(asyncio.get_running_loop())
        self._http.connector = aiohttp.TCPConnector(limit=0)
        self._http._HTTPClient__session = (  # type: ignore[attr-defined]
            aiohttp.ClientSession(
                connector=self._http.connector,
                trace_configs=(
                    None if self._http.http_trace is None else [self._http.http_trace]
                ),
                cookie_jar=aiohttp.DummyCookieJar(),
            )
        )
        self._http._global_over = asyncio.Event()
        self._http._global_over.set()
        self._http.token = self._token

    async def close(self) -> None:
        await self._http.close()

    @classmethod
    def from_dict(
        cls, global_cache: EmojiCache, hostname: str, data: Dict[str, Any]
    ) -> Self:
        return cls(
            global_cache,
            hostname,
            guild_id=data["guild_id"],
            token=data["token"],
            static_cache=dict(data["static"]),
            animated_cache=dict(data["animated"]),
        )

    def _emoji_uploader(
        self,
    ) -> Callable[[discord.PartialEmoji], Coroutine[None, None, discord.PartialEmoji]]:
        uploaded_count = 0
        allow_uploads = True

        async def upload(emoji: discord.PartialEmoji) -> discord.PartialEmoji:
            nonlocal allow_uploads, uploaded_count
            if not allow_uploads:
                raise RuntimeError
            if uploaded_count >= self.global_cache.per_msg_upload_limit:
                raise RuntimeError
            try:
                remote_emoji = await self.upload_emoji(emoji)
            except discord.Forbidden:
                log.warning("Could not upload emojis due to missing permissions")
                raise RuntimeError
            except discord.HTTPException as exc:
                log.error("Could not upload emojis due to HTTP error", exc_info=exc)
                raise RuntimeError
            except RuntimeError as exc:
                allow_uploads = False
                log.warning("%s", str(exc))
                raise RuntimeError
            assert emoji.id is not None, "mypy"
            if remote_emoji.animated:
                self._animated_cache[emoji.id] = str(remote_emoji)
            else:
                self._static_cache[emoji.id] = str(remote_emoji)
            uploaded_count += 1
            return remote_emoji

        return upload

    async def get_emoji_replacements(
        self, emojis: Iterable[discord.PartialEmoji]
    ) -> Tuple[Dict[str, str], bool]:
        static_replacements: Dict[str, str] = {}
        animated_replacements: Dict[str, str] = {}
        incomplete = False

        upload = self._emoji_uploader()
        for emoji in emojis:
            try:
                remote_emoji = self.get_remote_emoji(emoji)
            except KeyError:
                if (
                    len(static_replacements) == self.MAX_EMOJIS
                    or len(animated_replacements) == self.MAX_EMOJIS
                ):
                    # uploading would result in an earlier replacement not working
                    incomplete = True
                    continue
                try:
                    remote_emoji = await upload(emoji)
                except RuntimeError:
                    incomplete = True
                    continue

            if remote_emoji.animated:
                animated_replacements[str(emoji)] = str(remote_emoji)
            else:
                static_replacements[str(emoji)] = str(remote_emoji)

        await self.save_cache()

        return {**static_replacements, **animated_replacements}, incomplete

    def get_remote_emoji(self, emoji: discord.PartialEmoji) -> discord.PartialEmoji:
        # updates position in cache but does not save it
        assert emoji.id is not None, "mypy"
        try:
            raw_remote_emoji = self._static_cache.pop(emoji.id)
            self._static_cache[emoji.id] = raw_remote_emoji
        except KeyError:
            raw_remote_emoji = self._animated_cache.pop(emoji.id)
            self._animated_cache[emoji.id] = raw_remote_emoji
        return discord.PartialEmoji.from_str(raw_remote_emoji)

    async def get_or_upload_remote_emoji(
        self, emoji: discord.PartialEmoji
    ) -> discord.PartialEmoji:
        assert emoji.id is not None, "mypy"
        try:
            remote_emoji = self.get_remote_emoji(emoji)
        except KeyError:
            remote_emoji = await self.upload_emoji(emoji)

        if remote_emoji.animated:
            self._animated_cache[emoji.id] = str(remote_emoji)
        else:
            self._static_cache[emoji.id] = str(remote_emoji)
        await self.save_cache()

        return remote_emoji

    def _update_route_url(self, route: Route) -> Route:
        base_url = (
            f"https://{self.hostname}/api/v10"
            if self.hostname == "discord.com"
            else f"https://{self.hostname}/v1"
        )
        route.url = base_url + route.url[len(route.BASE) :]
        return route

    async def _delete_emoji(self, emoji_id: int, reason: str) -> None:
        route = Route(
            "DELETE",
            "/guilds/{guild_id}/emojis/{emoji_id}",
            guild_id=self.guild_id,
            emoji_id=emoji_id,
        )
        self._update_route_url(route)
        await self._http.request(route, reason=reason)

    async def upload_emoji(
        self,
        emoji: discord.PartialEmoji,
        *,
        delete_static: bool = False,
        delete_animated: bool = False,
    ) -> discord.PartialEmoji:
        delete_requested = delete_static or delete_animated
        if not delete_requested:
            if len(self._static_cache) == self.MAX_EMOJIS:
                delete_static = True
            if len(self._animated_cache) == self.MAX_EMOJIS:
                delete_animated = True
        for emoji_cache, should_delete in (
            (self._static_cache, delete_static),
            (self._animated_cache, delete_animated),
        ):
            if not should_delete:
                continue
            try:
                raw_emoji = emoji_cache.pop(next(iter(emoji_cache)))
            except StopIteration:
                raise RuntimeError("Emoji cache is empty but deletion was requested.")
            else:
                to_remove = discord.PartialEmoji.from_str(raw_emoji)

            assert to_remove.id is not None, "mypy"
            await self._delete_emoji(to_remove.id, "Fluxer bridge's emoji cache filled")

        route = Route("POST", "/guilds/{guild_id}/emojis", guild_id=self.guild_id)
        self._update_route_url(route)
        payload = {
            "name": emoji.name,
            # DEP-WARN
            "image": discord.utils._bytes_to_base64_data(await emoji.read()),
            "roles": [],
        }
        try:
            data = await self._http.request(
                route, json=payload, reason="Emoji cached by a fluxer bridge"
            )
        except discord.HTTPException as exc:
            if delete_requested:
                raise
            if IS_DISCORD:
                # Fluxer returns string error codes
                if exc.code == "MAX_EMOJIS":  # type: ignore[comparison-overlap]
                    return await self.upload_emoji(emoji, delete_static=True)
                if exc.code == (  # type: ignore[comparison-overlap]
                    "MAX_ANIMATED_EMOJIS"
                ):
                    return await self.upload_emoji(emoji, delete_animated=True)
            else:
                if exc.code == 30008:
                    return await self.upload_emoji(emoji, delete_static=True)
                if exc.code == 30018:
                    return await self.upload_emoji(emoji, delete_animated=True)
            raise

        if data.get("animated", False):
            return discord.PartialEmoji.from_str(f"<a:{data['name']}:{data['id']}>")
        return discord.PartialEmoji.from_str(f"<:{data['name']}:{data['id']}>")

    async def clear_all_remote_emojis(self) -> None:
        route = Route("GET", "/guilds/{guild_id}/emojis", guild_id=self.guild_id)
        self._update_route_url(route)
        data = await self._http.request(route)

        for raw_emoji in data:
            await self._delete_emoji(
                raw_emoji["id"],
                "Removing all emojis in Fluxer bridge emoji cache server",
            )

        await self.clear_cache()

    async def clear_cache(self) -> None:
        self._static_cache.clear()
        self._animated_cache.clear()
        await self.save_cache()

    async def save_cache(self) -> None:
        scope = self._cog.config.custom(EMOJI_CACHE, self.hostname)
        await scope.static.set(list(self._static_cache.items()))
        await scope.animated.set(list(self._animated_cache.items()))

    async def save_configuration(self) -> None:
        scope = self._cog.config.custom(EMOJI_CACHE, self.hostname)
        await scope.guild_id.set(self.guild_id)
        await scope.token.set(self._token)


class EmojiCache:
    def __init__(self, cog: FluxerBridge) -> None:
        self._cog = cog
        self._caches: Dict[str, InstanceEmojiCache] = {}
        self.per_msg_upload_limit = 0

    async def close(self) -> None:
        for cache in self._caches.values():
            await cache.close()

    def __getitem__(self, hostname: str) -> InstanceEmojiCache:
        return self._caches[hostname]

    def __setitem__(self, hostname: str, emoji_cache: InstanceEmojiCache) -> None:
        self._caches[hostname] = emoji_cache

    def __contains__(self, hostname: str) -> bool:
        return hostname in self._caches

    @overload
    def get(self, hostname: str, default: None = ...) -> Optional[InstanceEmojiCache]:
        ...

    @overload
    def get(self, hostname: str, default: T) -> Union[InstanceEmojiCache, T]:
        ...

    def get(
        self, hostname: str, default: Optional[T] = None
    ) -> Union[InstanceEmojiCache, T, None]:
        return self._caches.get(hostname, default)

    @overload
    def get_from_base_url(
        self, base_url: str, default: None = ...
    ) -> Optional[InstanceEmojiCache]:
        ...

    @overload
    def get_from_base_url(
        self, base_url: str, default: T
    ) -> Union[InstanceEmojiCache, T]:
        ...

    def get_from_base_url(
        self, base_url: str, default: Optional[T] = None
    ) -> Union[InstanceEmojiCache, T, None]:
        hostname = yarl.URL(f"https://{base_url}").host or ""
        return self._caches.get(hostname, default)

    def is_configured(self, hostname: str) -> bool:
        return hostname in self._caches

    async def initialize(self) -> None:
        raw_caches = await self._cog.config.custom(EMOJI_CACHE).all()
        self._caches = {
            hostname: InstanceEmojiCache.from_dict(self, hostname, data)
            for hostname, data in raw_caches.items()
        }
        self.per_msg_upload_limit = (
            await self._cog.config.emoji_cache_per_msg_upload_limit()
        )

    async def clear_configuration(self, hostname: str) -> None:
        await self._cog.config.custom(EMOJI_CACHE, hostname).clear()
        self._caches.pop(hostname, None)


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
            bots_allowed=False,
            bots_allowlist=[],
            bots_blocklist=[],
            emoji_cache_per_msg_upload_limit=3,
        )
        self.config.register_channel(webhook_data=None)
        # user id -> "local" message id -> {...}
        self.config.init_custom(USER_MESSAGES, 2)
        self.config.register_custom(USER_MESSAGES, remote_message_id=True)
        # "local" message id -> {...}
        self.config.init_custom(MESSAGES, 1)
        self.config.register_custom(MESSAGES, message_id=None, user_id=None)
        # base url hostname -> {...}
        self.config.init_custom(EMOJI_CACHE, 1)
        self.config.register_custom(
            EMOJI_CACHE, static=[], animated=[], guild_id=None, token=None
        )
        self._queue: asyncio.Queue[MessageEvent] = asyncio.Queue()
        self._queue_handler: Optional[asyncio.Task[None]] = None
        self.removed_bridges: Set[int] = set()
        # bot allow configuration
        self.bots_allowed = False
        self.bots_allowlist: Set[int] = set()
        self.bots_blocklist: Set[int] = set()
        self.emoji_cache = EmojiCache(self)

    async def initialize(self) -> None:
        self._session = aiohttp.ClientSession()
        await self.emoji_cache.initialize()
        self.bots_allowlist = set(await self.config.bots_allowlist())
        self.bots_blocklist = set(await self.config.bots_blocklist())
        self.bots_allowed = await self.config.bots_allowed()
        self._queue_handler = asyncio.create_task(self._handle_queue())

    async def cog_unload(self) -> None:
        if self._queue_handler is not None:
            self._queue_handler.cancel()
            try:
                await self._queue_handler
            except asyncio.CancelledError:
                pass
        await self.emoji_cache.close()
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

        has_downtime = False
        attempt = 0
        while True:
            if IS_DISCORD:
                # be aggressive on Fluxer early due to its instability and retry forever
                if has_downtime:
                    delay = 60.0 + random.random()
                elif attempt < 4:
                    delay = random.random()
                else:
                    delay = 2.0 ** ((attempt - 3) % 8)
                retry_on_fail = True
            else:
                delay = random.random() + 2.0 * attempt
                retry_on_fail = attempt < 9

            log_suffix = (
                f"Retrying in {delay:.2f}s." if retry_on_fail else "Will not retry."
            )
            had_downtime = has_downtime
            has_downtime = False
            try:
                try:
                    await event.execute()
                except discord.Forbidden:
                    if not IS_DISCORD:
                        raise
                    webhook = event._last_webhook
                    if webhook is None:
                        raise
                    async with self._session.get(
                        f"https://{webhook.red_webhook_base_url}/.well-known/fluxer"
                    ) as resp:
                        if resp.status != 403:
                            raise
                        raise FluxerMaintenanceError
            except FluxerMaintenanceError:
                has_downtime = True
                delay = 60.0 + random.random()
                if not had_downtime:
                    log.warning(
                        "Fluxer instance appears to be in maintenance,"
                        " slowing down retries... Next retry in %.2fs",
                        delay,
                    )
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

            if not retry_on_fail:
                break
            await asyncio.sleep(delay)
            if not has_downtime:
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

    @commands.is_owner()
    @fluxerbridge.group(name="emojis")
    async def fluxerbridge_emojis(self, ctx: commands.GuildContext) -> None:
        """
        Configure emoji cache server. This allows for emojis to work over the bridge.

        The emojis will get automatically uploaded to the emoji cache server
        and those emojis will be used for relayed messages.

        When the emoji cache fills up, emojis will be removed based on their last use
        (the least recently used will be removed first).
        """

    def _get_api_hostname(self, api_hostname: Optional[str] = None) -> str:
        if api_hostname is None:
            api_hostname = "api.fluxer.app" if IS_DISCORD else "discord.com"
        if api_hostname == "discordapp.com":
            api_hostname = "discord.com"
        if api_hostname not in VALID_API_HOSTNAMES:
            raise ValueError("The given API hostname is not valid.")
        return api_hostname

    @fluxerbridge_emojis.command(name="configure")
    async def fluxerbridge_emojis_configure(
        self, ctx: commands.GuildContext, guild_id: int
    ) -> None:
        """Configure the emoji cache server."""
        api_hostname = self._get_api_hostname()
        if self.emoji_cache.is_configured(api_hostname):
            command = inline(f"{ctx.prefix}fluxerbridge emojis reset")
            await ctx.send(
                f"An emoji cache is already configured for {api_hostname}."
                f" If you want to reconfigure, run {command} first."
            )
            return

        try:
            dm_msg = await ctx.author.send(
                "Send token for a bot with Manage Emojis permissions in the server"
                " you provided ID of in the next message."
            )
        except discord.Forbidden:
            await ctx.send("I couldn't send you a DM.")
            return

        try:
            msg = await self.bot.wait_for(
                "message",
                check=MessagePredicate.same_context(channel=dm_msg.channel),
                timeout=60,
            )
        except asyncio.TimeoutError:
            await ctx.author.send("Timed out.")
            return

        emoji_cache = InstanceEmojiCache(
            self.emoji_cache, api_hostname, guild_id=guild_id, token=msg.content
        )
        await emoji_cache.save_cache()
        await emoji_cache.save_configuration()
        self.emoji_cache[api_hostname] = emoji_cache

        await ctx.send("The emoji cache server has been configured.")

    @fluxerbridge_emojis.command(name="reset")
    async def fluxerbridge_emojis_reset(self, ctx: commands.GuildContext) -> None:
        """Reset the emoji cache server configuration and clear the cache."""
        api_hostname = self._get_api_hostname()
        if api_hostname not in self.emoji_cache:
            await ctx.send(f"There is no emoji cache server for {api_hostname}!")
            return

        await self.emoji_cache.clear_configuration(api_hostname)

        await ctx.send("The emoji cache server configuration has been reset.")

    @fluxerbridge_emojis.command(name="removeall")
    async def fluxerbridge_emojis_removeall(
        self, ctx: commands.GuildContext, *, api_hostname: Optional[str] = None
    ) -> None:
        """
        Remove all emojis (tracked and untracked) in the configured emoji cache server.
        """
        api_hostname = self._get_api_hostname()
        try:
            emoji_cache = self.emoji_cache[api_hostname]
        except KeyError:
            await ctx.send(f"There is no emoji cache server for {api_hostname}!")
            return

        query = await ctx.send(
            "Are you sure that you want to remove all emojis (including ones"
            " not created by the bot) in the emoji cache server"
            f" (ID: {emoji_cache.guild_id}) you have configured for {api_hostname})?"
            " This action cannot be reverted."
        )
        start_adding_reactions(query, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(query, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
        except asyncio.TimeoutError:
            await ctx.send("Timed out.")
            return
        if not pred.result:
            await ctx.send("OK then.")
            return

        async with ctx.typing():
            await emoji_cache.clear_all_remote_emojis()

        await ctx.send(
            "All emojis have been removed from the configured emoji cache server."
        )

    @fluxerbridge_emojis.command(name="uploadlimit")
    async def fluxerbridge_emojis_maxuploadlimit(
        self, ctx: commands.GuildContext, *, value: commands.Range[int, 0, 50]
    ) -> None:
        """
        Set the max number of emojis that can be uploaded to cache by a single message.

        Any emoji over this limit that's not already cached will not be replaced
        with valid emojis and will show as: `:emojiname:`

        This directly affects performance of the bridges as each emoji upload
        requires 2 additional API requests to download and upload that emoji.

        You can set this to 0 to effectively stop caching new emojis
        and avoid the performance penalty. This also allows to populate the cache
        with emojis of your choice by first setting the limit to max value (50),
        sending a message with emojis you'd like to work in the relayed messages
        and then setting it to 0 to prevent further modifications.
        """
        await self.config.emoji_cache_per_msg_upload_limit.set(value)
        self.emoji_cache.per_msg_upload_limit = value
        await ctx.send(f"The new per-message upload limit has been set to {value}.")

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

        try:
            msg = await self.bot.wait_for(
                "message", check=MessagePredicate.same_context(channel=dm_msg.channel)
            )
        except asyncio.TimeoutError:
            await ctx.author.send("Timed out.")
            return
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
        if webhook_base_url == "discordapp.com/api":
            webhook_base_url = "discord.com/api"

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
