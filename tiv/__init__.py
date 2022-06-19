# Copyright 2018-present Jakub Kuczys (https://github.com/jack1142)
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

import json
from pathlib import Path

import discord
from discord.ext import commands as dpy_commands
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.errors import CogLoadError

from .tiv import _tiv_load, _tiv_unload, clear_abc_caches

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


async def setup(bot: Red) -> None:
    if discord.version_info.major == 2:
        raise CogLoadError("Text in Voice Channels support is built into Red 3.5!")

    detected_bug = False
    for cls in (
        discord.Member,
        discord.User,
        discord.DMChannel,
        discord.TextChannel,
        dpy_commands.Context,
        commands.Context,
    ):
        if issubclass(discord.VoiceChannel, cls):
            detected_bug = True
            clear_abc_caches(cls)

    if detected_bug:
        raise CogLoadError(
            "While loading this cog, a crash-inducing bug that an earlier version"
            " of TiV accidentally introduces has been detected. TiV made an attempt at"
            " autofixing it but it is recommended that you restart your bot"
            " as soon as possible. Sorry about that!\n\n"
            "Current version of TiV no longer introduces this issue and there are"
            " no known crash-inducing bugs in it."
        )

    _tiv_load()


def teardown(bot: Red) -> None:
    _tiv_unload()
