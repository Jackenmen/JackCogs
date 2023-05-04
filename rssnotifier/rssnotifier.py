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
import itertools
from io import BytesIO
from typing import Any, Dict, List, Literal, Union

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands import GuildContext, NoParseOptional as Optional
from redbot.core.config import Config
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import inline, pagify

from .checks import single_user_pings_enabled
from .converters import RawRoleObjectConverter as RawRoleObject

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]
FEED = "FEED"


class RSSNotifier(commands.Cog):
    """Get role and/or user mentions about feed updates."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, 176070082584248320, force_registration=True)
        self.config.register_guild(ping_single_users=False)
        # {CHANNEL_ID: {FEED_NAME: {...}}}
        self.config.init_custom(FEED, 2)
        self.config.register_custom(FEED, user_mentions=[], role_mentions=[])

    async def red_get_data_for_user(self, *, user_id: int) -> Dict[str, BytesIO]:
        fp = BytesIO()
        fp.write(
            f"Feeds which the Discord user with ID {user_id}"
            " opted in receiving notifications for (grouped by channel):\n".encode()
        )
        all_feed_data = await self.config.custom(FEED).all()
        async for channel_id_str, feeds in AsyncIter(all_feed_data.items(), steps=100):
            channel_name: Optional[str] = None
            for feed_name, feed_data in feeds.items():
                if user_id not in feed_data["user_mentions"]:
                    continue
                if channel_name is None:
                    # channel name header has't been added yet
                    channel = self.bot.get_channel(int(channel_id_str))
                    if channel is not None:
                        assert isinstance(channel, discord.abc.GuildChannel)
                        channel_name = (
                            f"#{channel} ({channel.id}) in {channel.guild} server"
                        )
                    else:
                        channel_name = (
                            f"[Unknown or Deleted Channel] ({channel_id_str})"
                        )
                    fp.write(f"- {channel_name}\n".encode())
                fp.write(b"    - ")
                fp.write(feed_name.encode())
                fp.write(b"\n")
        fp.seek(0)

        return {"user_data.txt": fp}

    async def red_delete_data_for_user(
        self, *, requester: RequestType, user_id: int
    ) -> None:
        all_feed_data = await self.config.custom(FEED).all()
        async for channel_id_str, feeds in AsyncIter(all_feed_data.items(), steps=100):
            for feed_name, feed_data in feeds.items():
                if user_id not in feed_data["user_mentions"]:
                    continue
                scope = self.config.custom(
                    FEED, channel_id_str, feed_name
                ).user_mentions
                # we want the lock to do its job here
                async with scope() as user_mentions:
                    # in case loop context switches on us
                    with contextlib.suppress(ValueError):
                        user_mentions.remove(user_id)

    @commands.guild_only()
    @commands.group()
    async def rssnotifier(self, ctx: GuildContext) -> None:
        """RSSNotifier settings."""

    @commands.admin_or_can_manage_channel()
    @rssnotifier.command(
        name="addroles", aliases=["addrole"], usage="<feed_name> <channel> <roles...>"
    )
    async def rssnotifier_addroles(
        self,
        ctx: GuildContext,
        feed_name: str,
        channel: Union[
            discord.TextChannel,
            discord.VoiceChannel,
            discord.StageChannel,
            discord.Thread,
        ],
        *roles: discord.Role,
    ) -> None:
        """
        Add roles that should be mentioned when new message for given feed is sent.

        Use `[p]rss list` for the list of available feeds.
        """
        if not roles:
            await ctx.send_help()
            return

        scope = self.config.custom(FEED, channel.id, feed_name).role_mentions
        async with scope() as role_mentions:
            for role in roles:
                if role.id not in role_mentions:
                    role_mentions.append(role.id)

        await ctx.send(
            "Given roles have been added to mentions list"
            f" for feed {inline(feed_name)} in {channel.mention}."
        )

    @commands.admin_or_can_manage_channel()
    @rssnotifier.command(
        name="removeroles",
        aliases=["removerole"],
        usage="<feed_name> <channel> <roles...>",
    )
    async def rssnotifier_removeroles(
        self,
        ctx: GuildContext,
        feed_name: str,
        channel: Union[
            discord.TextChannel,
            discord.VoiceChannel,
            discord.StageChannel,
            discord.Thread,
        ],
        # support the int for the cases where the role no longer exists
        *roles: RawRoleObject,
    ) -> None:
        """
        Remove roles that should be mentioned when new message for given feed is sent.

        Use `[p]rss list` for the list of available feeds.
        """
        if not roles:
            await ctx.send_help()
            return

        scope = self.config.custom(FEED, channel.id, feed_name).role_mentions
        async with scope() as role_mentions:
            for role in roles:
                with contextlib.suppress(ValueError):
                    role_mentions.remove(role.id)

        await ctx.send(
            "Given roles have been removed from mentions list"
            f" for feed {inline(feed_name)} in {channel.mention}."
        )

    @commands.admin_or_can_manage_channel()
    @rssnotifier.command(name="listroles")
    async def rssnotifier_listroles(
        self,
        ctx: GuildContext,
        feed_name: str,
        channel: Optional[
            Union[
                discord.TextChannel,
                discord.VoiceChannel,
                discord.StageChannel,
                discord.Thread,
            ]
        ] = None,
    ) -> None:
        """
        List role mentions list for the given feed name.

        Use `[p]rss list` for the list of available feeds.
        """
        channel = channel or ctx.channel

        role_ids = await self.config.custom(FEED, channel.id, feed_name).role_mentions()
        role_list = "\n".join(map("- <@&{}>".format, role_ids))
        # this should realistically never reach second page
        for page in pagify(
            f"List of roles that will be pinged for {inline(feed_name)} feed"
            f" in {channel.mention}:\n{role_list}"
        ):
            await ctx.send(page)

    @commands.admin_or_can_manage_channel()
    @rssnotifier.command(name="usermentions")
    async def rssnotifier_usermentions(
        self, ctx: GuildContext, state: Optional[bool] = None
    ) -> None:
        """
        Set whether users can opt-in receiving notifications.

        **NOTE:** Generally, it is better to use role mentions
        and allow the users to self-assign the set role
        rather than have the bot send a lot of single user mentions.

        This setting applies to whole server.

        When this is enabled, users can use `[p]rssnotifier optin/optout`
        to opt-in/opt-out of receiving notifications for given rss feed.

        When this is disabled, cog will ignore any users who have previously opted-in
        and only mention the roles set by server admins.

        By default this is disabled
        and only the roles set by server admins will be mentioned.
        """
        if state is None:
            if await self.config.guild(ctx.guild).ping_single_users():
                msg = "User are allowed to opt-in receiving notifications."
            else:
                msg = "User aren't allowed to opt-in receiving notifications."
            await ctx.send(msg)
            return

        if state:
            msg = "User can now opt-in receiving notifications."
        else:
            msg = "User can now no longer opt-in receiving notifications."
        await self.config.guild(ctx.guild).ping_single_users.set(state)
        await ctx.send(msg)

    @single_user_pings_enabled()
    @rssnotifier.command(name="optin")
    async def rssnotifier_optin(
        self,
        ctx: GuildContext,
        feed_name: str,
        channel: Optional[
            Union[
                discord.TextChannel,
                discord.VoiceChannel,
                discord.StageChannel,
                discord.Thread,
            ]
        ] = None,
    ) -> None:
        """
        Opt-in receiving notifications for the given feed name.

        Use `[p]rss list` for the list of available feeds.
        """
        user_id = ctx.author.id
        if channel is None:
            channel = ctx.channel
        scope = self.config.custom(FEED, channel.id, feed_name).user_mentions
        async with scope.get_lock():
            user_mentions = await scope()
            if user_id in user_mentions:
                await ctx.send(
                    "You already opted in receiving notifications for this feed."
                )
                return
            user_mentions.append(user_id)
            await scope.set(user_mentions)
            await ctx.send(
                "You will now receive notifications"
                f" for feed {inline(feed_name)} in {channel.mention}."
            )

    @single_user_pings_enabled()
    @rssnotifier.command(name="optout")
    async def rssnotifier_optout(
        self,
        ctx: GuildContext,
        feed_name: str,
        channel: Optional[
            Union[
                discord.TextChannel,
                discord.VoiceChannel,
                discord.StageChannel,
                discord.Thread,
            ]
        ] = None,
    ) -> None:
        """
        Opt-out of receiving notifications for the given feed name.

        Use `[p]rss list` for the list of available feeds.
        """
        user_id = ctx.author.id
        if channel is None:
            channel = ctx.channel
        scope = self.config.custom(FEED, channel.id, feed_name).user_mentions
        async with scope.get_lock():
            user_mentions = await scope()
            if user_id not in user_mentions:
                await ctx.send("You weren't registered to notifications for this feed.")
                return
            user_mentions.remove(user_id)
            await scope.set(user_mentions)
            await ctx.send(
                "You will no longer receive notifications"
                f" for feed {inline(feed_name)} in {channel.mention}."
            )

    @commands.admin_or_can_manage_channel()
    @rssnotifier.command(name="adminoptout")
    async def rssnotifier_adminoptout(
        self,
        ctx: GuildContext,
        feed_name: str,
        channel: Union[
            discord.TextChannel,
            discord.VoiceChannel,
            discord.StageChannel,
            discord.Thread,
        ],
        *user_ids: int,
    ) -> None:
        """
        Force opt-out the users with given IDs from the given feed.

        This can be useful, when the user is no longer in server, for example.

        Use `[p]rss list` for the list of available feeds.
        """
        if not user_ids:
            await ctx.send_help()
            return

        scope = self.config.custom(FEED, channel.id, feed_name).user_mentions
        async with scope() as user_mentions:
            for user_id in user_ids:
                with contextlib.suppress(ValueError):
                    user_mentions.remove(user_id)
        await ctx.send(
            "Users with given IDs have been forcefully opted-out of"
            f" receiving notifications for feed {inline(feed_name)}"
            f" in {channel.mention}."
        )

    @commands.Cog.listener()
    async def on_aikaternacogs_rss_feed_update(
        self,
        *,
        channel: Union[
            discord.TextChannel,
            discord.VoiceChannel,
            discord.StageChannel,
            discord.Thread,
        ],
        feed_data: Dict[str, Any],
        force: bool,
        **_kwargs: Any,
    ) -> None:
        """
        Ping roles and users when rss message is sent.

        Listener documentation:
        https://github.com/aikaterna/aikaterna-cogs/blob/8b043d81a87e96b51bee1e1e17a11f60f2bf61c2/rss/rss.py#L719-L734
        """
        guild = channel.guild
        # We don't need to check whether RSS is enabled
        # as it wouldn't send the event if it were.
        if await self.bot.cog_disabled_in_guild(self, guild):
            return

        feed_name = feed_data["name"]
        ping_single_users = await self.config.guild(guild).ping_single_users()
        feed_scope = self.config.custom(FEED, channel.id, feed_name)
        if ping_single_users:
            config_data = await feed_scope.all()
            role_mentions = config_data["role_mentions"]
            user_mentions = config_data["user_mentions"]
        else:
            role_mentions = await feed_scope.role_mentions()
            user_mentions = []

        if not (user_mentions or role_mentions):
            return
        if force:
            await channel.send(
                "THIS IS A FORCED UPDATE. RSSNotifier will not notify users about it."
            )
            return

        collected_role_mentions = []
        for role_id in role_mentions:
            role = guild.get_role(role_id)
            if role is not None:
                collected_role_mentions.append(role_id)
        collected_user_mentions: List[int] = []
        allowed_mentions = discord.AllowedMentions(roles=True)
        for page in pagify(
            " ".join(
                itertools.chain(
                    map("<@&{}>".format, collected_role_mentions),
                    map("<@{}>".format, user_mentions),
                )
            ),
            delims=[" "],
        ):
            msg = await channel.send(page, allowed_mentions=allowed_mentions)
            collected_user_mentions.extend(u.id for u in msg.mentions)

        if len(collected_user_mentions) != len(user_mentions):
            # this will change the order of the mentions but it's not an issue IMO
            await feed_scope.user_mentions.set(collected_user_mentions)

        if len(collected_role_mentions) != len(role_mentions):
            await feed_scope.role_mentions.set(collected_role_mentions)
