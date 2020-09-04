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

import asyncio
from typing import Any, Dict, Literal

import aiohttp
import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.config import Config

from .ipykernel_utils import RedIPKernelApp, embed_kernel

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]


class Qupyter(commands.Cog):
    """Run IPython kernel within Red and connect to it with Jupyter Console."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, 176070082584248320, force_registration=True)
        self.env = {
            "bot": bot,
            "aiohttp": aiohttp,
            "asyncio": asyncio,
            "discord": discord,
            "commands": commands,
        }
        self.app: RedIPKernelApp

    def init(self) -> None:
        """Post-add cog initialization."""
        self.app = embed_kernel(self.env)

    def cog_unload(self) -> None:
        """Cog unload cleanup."""
        self.app.cleanup_connection_file()
        self.app.close()

    async def red_get_data_for_user(self, *, user_id: int) -> Dict[str, Any]:
        # this cog does not story any data
        return {}

    async def red_delete_data_for_user(
        self, *, requester: RequestType, user_id: int
    ) -> None:
        # this cog does not story any data
        pass
