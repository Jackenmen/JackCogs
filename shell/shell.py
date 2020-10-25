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
import asyncio.subprocess as asp
import contextlib
from typing import Any, Dict, List, Literal

from redbot.core import commands
from redbot.core.bot import Red

from .errors import ProcessTerminatedEarly
from .utils import get_env, send_pages, wait_for_result

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]


class Shell(commands.Cog):
    """Run shell commands on bot's system from Discord."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.active_processes: List[asp.Process] = []
        self._killing_lock = asyncio.Lock()

    async def red_get_data_for_user(self, *, user_id: int) -> Dict[str, Any]:
        # this cog does not story any data
        return {}

    async def red_delete_data_for_user(
        self, *, requester: RequestType, user_id: int
    ) -> None:
        # this cog does not story any data
        pass

    @commands.is_owner()
    @commands.command()
    async def shell(self, ctx: commands.Context, *, command: str) -> None:
        """Run shell command."""
        await self._shell_command(ctx, command)

    @commands.is_owner()
    @commands.command()
    async def shellq(self, ctx: commands.Context, *, command: str) -> None:
        """
        Run shell command quietly.

        If command's exit code is 0, `[p]shellq` will only send a tick reaction.
        Otherwise, the result will be shown as with regular `[p]shell` command.
        """
        await self._shell_command(ctx, command, send_message_on_success=False)

    async def _shell_command(
        self,
        ctx: commands.Context,
        command: str,
        *,
        send_message_on_success: bool = True,
    ) -> None:
        async with ctx.typing():
            async with self._killing_lock:
                p = await asp.create_subprocess_shell(
                    command, stdout=asp.PIPE, stderr=asp.STDOUT, env=get_env()
                )
                self.active_processes.append(p)

            try:
                output = await wait_for_result(p)
            except ProcessTerminatedEarly as e:
                output = e.partial_output
                prefix = (
                    "**Command was terminated early and this is a partial output.**\n"
                )
            else:
                prefix = ""

            async with self._killing_lock:
                with contextlib.suppress(ValueError):
                    self.active_processes.remove(p)

        if not send_message_on_success and p.returncode == 0:
            await ctx.tick()
        else:
            await send_pages(ctx, command=command, output=output, prefix=prefix)

    @commands.is_owner()
    @commands.command()
    async def killshells(self, ctx: commands.Context) -> None:
        """Kill all shell processes started by Shell cog."""
        async with self._killing_lock:
            for p in reversed(self.active_processes):
                # in case some Process is still here after it terminated
                if p.returncode is None:
                    p.kill()
                self.active_processes.pop()
        await ctx.send("Killed all active shell processes.")
