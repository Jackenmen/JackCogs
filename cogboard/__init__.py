# Copyright 2018-2021 Jakub Kuczys (https://github.com/jack1142)
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

from redbot.core.bot import Red
from redbot.core.errors import CogLoadError

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


def setup(bot: Red) -> None:
    raise CogLoadError(
        "CogBoard cog has been removed from JackCogs repo on 16.01.2021"
        " and is no longer supported.\n"
        "A better alternative - the Index cog using Red-Index backend"
        " - can be found in the x26-Cogs repository:\n"
        "https://github.com/Twentysix26/x26-Cogs\n\n"
        "If you have any questions,"
        " ask on Cog Support server in #support_othercogs channel.\n"
        "https://discord.gg/GET4DVk"
    )
