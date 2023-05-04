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

from typing import TYPE_CHECKING, Callable, TypeVar, cast

from redbot.core import commands

if TYPE_CHECKING:
    from .rssnotifier import RSSNotifier
else:
    RSSNotifier = ...

_T = TypeVar("_T")


def single_user_pings_enabled() -> Callable[[_T], _T]:
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False
        cog = cast(RSSNotifier, ctx.cog)
        ping_single_users = await cog.config.guild(ctx.guild).ping_single_users()
        if ping_single_users:
            return True
        raise commands.CheckFailure(
            "User mentions in RSSNotifier are disabled for this server."
        )

    return commands.check(predicate)
