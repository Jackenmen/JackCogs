# Copyright 2018-2020 Jakub Kuczys (https://github.com/jack1142)
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
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from redbot.core.bot import Red
from redbot.core.errors import CogLoadError

if sys.platform == "win32" and not TYPE_CHECKING:
    raise CogLoadError("This cog does not support Windows.")

from .depr_warnings import ignore_ipy_depr_warnings

ignore_ipy_depr_warnings()

from .qupyter import Qupyter  # noqa: E402

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


async def setup(bot: Red) -> None:
    cog = Qupyter(bot)
    bot.add_cog(cog)
    await cog.initialize()
