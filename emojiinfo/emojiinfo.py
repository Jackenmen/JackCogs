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

from typing import Any, Dict, Literal

from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify

from .utils import iter_emojis

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]


class EmojiInfo(commands.Cog):
    """Get information about emojis and see how to use them in your code."""

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

    @commands.command(usage="<emoji>...")
    async def emojiinfo(self, ctx: commands.Context, *, raw_emojis: str) -> None:
        """
        Get detailed information about passed emojis.

        Non-emoji characters are ignored.
        """
        msg = "".join(
            f"{emoji}```{emoji_repr}```"
            for emoji, emoji_repr in iter_emojis(raw_emojis)
        )
        if not msg:
            await ctx.send("No valid emojis were passed.")
            return
        await ctx.send_interactive(pagify(msg))
