"""
Copyright 2018-2020 Jakub Kuczys (https://github.com/jack1142)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from redbot.core.bot import Red
from redbot.core.errors import CogLoadError

try:
    from .rlstats import RLStats
except ModuleNotFoundError as e:
    if e.name == "PIL":
        raise CogLoadError(
            "You need `pillow` pip package to run this cog."
            " Downloader *should* have handled this for you."
        )
    if e.name == "rlapi":
        raise CogLoadError(
            "You need `rlapi` pip package to run this cog."
            " Downloader *should* have handled this for you."
        )
    raise

__red_end_user_data_statement__ = (
    "This cog stores data provided by users"
    " for the purpose of better user experience.\n"
    "It does not store user data which was not provided through a command.\n"
    "Users may remove their own data without making a data removal request.\n"
    "This cog will remove data when a data removal request is made."
)


async def setup(bot: Red) -> None:
    cog = RLStats(bot)
    await cog.initialize()
    bot.add_cog(cog)
