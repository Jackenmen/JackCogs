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

import asyncio
import asyncio.subprocess as asp
import contextlib
import os
from typing import Any, Dict, List, Literal

from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands import NoParseOptional as Optional
from redbot.core.config import Config
from redbot.core.utils.chat_formatting import inline

from .errors import ProcessTerminatedEarly
from .utils import get_env, send_pages, strip_code_block, wait_for_result

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]


class Shell(commands.Cog):
    """Run shell commands on bot's system from Discord."""

    replacement_shell: Optional[str]

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, 176070082584248320, force_registration=True)
        self.config.register_global(
            replacement_shell=None,
            env_modifications={"TERM": "xterm-16color"},
        )
        self.active_processes: List[asp.Process] = []
        self._killing_lock = asyncio.Lock()

    async def initialize(self) -> None:
        self.replacement_shell = (
            await self.config.replacement_shell() if os.name == "posix" else None
        )

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

    async def _get_env(self) -> None:
        env = get_env()
        env_modifications = await self.config.env_modifications()
        for variable_name, value in env_modifications.items():
            if value is None:
                env.pop(variable_name, None)
            else:
                env[variable_name] = value
        return env

    async def _shell_command(
        self,
        ctx: commands.Context,
        command: str,
        *,
        send_message_on_success: bool = True,
    ) -> None:
        command = strip_code_block(command)
        async with ctx.typing():
            async with self._killing_lock:
                try:
                    p = await asp.create_subprocess_shell(
                        command,
                        stdout=asp.PIPE,
                        stderr=asp.STDOUT,
                        env=await self._get_env(),
                        executable=self.replacement_shell,
                    )
                except (FileNotFoundError, NotADirectoryError, PermissionError):
                    command_1 = inline(f"{ctx.clean_prefix}shellset shell")
                    command_2 = inline(f"{ctx.clean_prefix}shellset shell reset")
                    await ctx.send(
                        "It appears the shell you have set does not exist."
                        f" Try to set another one with {command_1} or reset it to"
                        f" default with {command_2}."
                    )
                    return
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

    @commands.is_owner()
    @commands.group()
    async def shellset(self, ctx: commands.Context) -> None:
        """Manage settings of the Shell cog."""

    @shellset.group(name="env")
    async def shellset_env(self, ctx: commands.Context) -> None:
        """Manage environment variables all shell processes start with."""

    @shellset_env.command(name="list")
    async def shellset_env_list(
        self, ctx: commands.Context, variable_name: str, *, value: str
    ) -> None:
        """List preferences about environment variables set for all shell processes."""
        env_modifications = await self.config.env_modifications()
        custom_vars = []
        ensure_unset = []
        for variable_name, value in env_modifications.items():
            if value is None:
                ensure_unset.append(variable_name)
            else:
                custom_vars.append((variable_name, value))

        output = [
            "Cog ensures that these environment variables are not set:",
            ", ".join(ensure_unset),
            "These environment variables are set with custom values"
            " for all shell processes:",
        ]

        for variable_name, value in custom_vars:
            output.append(f"- {inline(variable_name)}: {inline(value)}")

        await ctx.send("\n".join(output))

    @shellset_env.command(name="add")
    async def shellset_env_add(
        self, ctx: commands.Context, variable_name: str, *, value: str
    ) -> None:
        """Add environment variable to be set for all shell processes."""
        async with self.config.env_modifications() as env_modifications:
            if (
                variable_name in env_modifications
                and env_modifications[variable_name] is not None
            ):
                command = inline(f"{ctx.clean_prefix}shellset env update")
                await ctx.send(
                    f"An environment variable {inline(variable_name)} already exists."
                    f" If you want to update its value, use {command} instead."
                )
                return
            env_modifications[variable_name] = value
        await ctx.send(
            f"The environment variable {inline(variable_name)} has been added."
        )

    @shellset_env.command(name="update")
    async def shellset_env_update(
        self, ctx: commands.Context, variable_name: str, *, value: str
    ) -> None:
        """Update value of an added environment variable."""
        async with self.config.env_modifications() as env_modifications:
            env_modifications[variable_name] = value
        await ctx.send(
            f"The environment variable {inline(variable_name)} has been updated."
        )

    @shellset_env.command(name="remove")
    async def shellset_env_remove(
        self, ctx: commands.Context, variable_name: str
    ) -> None:
        """Remove environment variable to be set for all shell processes."""
        async with self.config.env_modifications() as env_modifications:
            try:
                value = env_modifications[variable_name]
            except KeyError:
                await ctx.send(
                    f"An environment variable {inline(variable_name)} does not exist."
                )
                return
            if value is None:
                command = inline(f"{ctx.clean_prefix}shellset env ignoreunset")
                await ctx.send(
                    "The cog is set to ensure that the environment variable is not set."
                    " To no longer ensure that the environment variable is not set,"
                    f" use {command}."
                )
                return
            del env_modifications[variable_name]
        await ctx.send(
            f"The environment variable {inline(variable_name)} has been removed."
        )

    @shellset_env.group(name="ensureunset")
    async def shellset_env_ensureunset(
        self, ctx: commands.Context, variable_name: str
    ) -> None:
        """Ensure that the environment variable is not set."""
        async with self.config.env_modifications() as env_modifications:
            env_modifications[variable_name] = None
        await ctx.send(
            "The cog will now ensure that the environment variable"
            f" {inline(variable_name)} is not set."
        )

    @shellset_env.group(name="ignoreunset")
    async def shellset_env_ignoreunset(
        self, ctx: commands.Context, variable_name: str
    ) -> None:
        """Ignore whether the environment variable is not set."""
        async with self.config.env_modifications() as env_modifications:
            if (
                variable_name not in env_modifications
                or env_modifications[variable_name] is not None
            ):
                await ctx.send(
                    "The cog wasn't set to ensure that the environment variable"
                    " is not set. No changes have been made."
                )
                return
            del env_modifications[variable_name]
        await ctx.send(
            "The cog will no longer ensure that the environment variable"
            f" {inline(variable_name)} is not set."
        )

    if os.name == "posix":

        @shellset.group(name="shell", invoke_without_command=True)
        async def shellset_shell(
            self, ctx: commands.Context, replacement_shell: str
        ) -> None:
            """
            Set a replacement shell for the default ``/bin/sh``.

            This needs to be a full path to the replacement shell.
            The input is not validated.

            Only works on POSIX systems.
            """
            await self.config.replacement_shell.set(replacement_shell)
            self.replacement_shell = replacement_shell
            await ctx.send("This shell will now be used instead of the default.")

        @shellset_shell.command(name="reset")
        async def shellset_shell_reset(self, ctx: commands.Context) -> None:
            """Reset the replacement shell back to the default."""
            await self.config.replacement_shell.clear()
            self.replacement_shell = None
            await ctx.send("The default shell will now be used.")
