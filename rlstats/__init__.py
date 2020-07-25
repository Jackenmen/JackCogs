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

from redbot import version_info, VersionInfo
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

if version_info < VersionInfo.from_str("3.2.0"):
    raise CogLoadError(
        "This cog requires at least Red 3.2.0. Update the bot to be able to use"
        " the **latest, supported** version of this cog.\n"
        "If you want to continue using this cog on Red 3.1.x, you will have to"
        ' add my repo with "rlstats-3.1" passed on branch argument like so:\n'
        "`[p]repo add JackCogs-31 https://github.com/jack1142/JackCogs rlstats-3.1`"
        "\nKeep in mind that 3.1 version of rlstats cog is **no longer supported**"
        " and won't get any updates."
    )


async def setup(bot: Red) -> None:
    cog = RLStats(bot)
    await cog.initialize()
    bot.add_cog(cog)
