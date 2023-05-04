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

import asyncio
import shutil
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import aiohttp
import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.config import Config
from redbot.core.data_manager import cog_data_path

from .converters import PortNumber
from .ipykernel_utils import RedIPKernelApp, clear_singleton_instances, embed_kernel

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]
_PORT_NAMES = ("shell_port", "iopub_port", "stdin_port", "hb_port", "control_port")


class Qupyter(commands.Cog):
    """Run IPython kernel within Red and connect to it with Jupyter Console."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, 176070082584248320, force_registration=True)
        self.config.register_global(execution_key=None, ports=None)
        self.env = {
            "bot": bot,
            "aiohttp": aiohttp,
            "asyncio": asyncio,
            "discord": discord,
            "commands": commands,
        }
        self.connection_file = cog_data_path(self) / "kernel.json"
        self.app: Optional[RedIPKernelApp] = None

    async def initialize(self) -> None:
        """Post-add cog initialization."""
        await self.start_app()

    async def cog_unload(self) -> None:
        """Cog unload cleanup."""
        self.stop_app()

    async def start_app(self) -> None:
        if self.app is not None:
            raise RuntimeError("App is already running!")

        data = await self.config.all()
        ports = data["ports"]
        execution_key = data["execution_key"]
        kwargs: Dict[str, Any] = {}
        if ports is not None:
            kwargs.update(zip(_PORT_NAMES, ports))
        if execution_key is not None:
            kwargs.update(execution_key=execution_key.encode("ascii"))

        self.app = app = embed_kernel(self.env, **kwargs)

        self.connection_file.unlink(missing_ok=True)
        connection_file = Path(app.connection_dir) / app.connection_file
        shutil.copy(connection_file, self.connection_file)

    def stop_app(self) -> None:
        if self.app is not None:
            self.connection_file.unlink(missing_ok=True)
            self.app.cleanup_connection_file()
            self.app.close()
            self.app = None
        # needed for proper hot-reload
        clear_singleton_instances()

    async def restart_app(self) -> None:
        self.stop_app()
        await self.start_app()

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
    async def qupyctx(self, ctx: commands.Context) -> None:
        """
        Update kernel's environment with variables from current invocation context.

        This command assigns relevant d.py objects from current invocation context
        to `ctx`, `author`, `channel`, `guild`, and `message` variables
        in kernel's environment.

        This will override any current values that are assigned
        under these variable names.
        """
        self.env.update(
            ctx=ctx,
            author=ctx.author,
            channel=ctx.channel,
            guild=ctx.guild,
            message=ctx.message,
        )
        await ctx.send(
            "Kernel's environment updated with variables"
            " from current invocation context."
        )

    @commands.is_owner()
    @commands.group()
    async def qupyterset(self, ctx: commands.Context) -> None:
        """Qupyter settings."""

    @qupyterset.command(name="explain")
    async def qupyterset_explain(self, ctx: commands.Context) -> None:
        """Explain how to use Qupyter."""
        p = ctx.clean_prefix
        await ctx.send(
            "This cog runs a kernel application that allows you to run any IPython code"
            " within Red's environment. You can connect to it"
            " using `jupyter console` client.\n"
            "If you're using `jupyter console` on the host machine and you're not"
            " running other Jupyter kernels (on another bot for example), it should be"
            " enough to run `jupyter console --existing` which will make Jupyter try to"
            " connect to the most recently started kernel. If that doesn't work,"
            " you can explicitly pass path to connection file that is located"
            " in cog's data path:```"
            "jupyter console --existing <data_path>/cogs/Qupyter/kernel.json"
            "```\n"
            "Alternatively, if you want to use `jupyter console` from"
            " a different machine, you can copy the connection file"
            f" and tunnel the ports from the host machine. `{p}qupyterset freezekey`"
            f" and `{p}qupyterset setports` commands can make this process easier"
            " by keeping the connection details the same between cog reloads."
        )

    @qupyterset.command(name="freezekey")
    async def qupyterset_freezekey(self, ctx: commands.Context) -> None:
        """
        Freeze the execution key used for signing messages.

        This ensures that the execution key will be the same between cog reloads.

        Useful (along with port settings), if you don't want to get the connection file
        from the host machine each time you try to connect to the kernel from different
        machine.
        """
        if self.app is None:
            await ctx.send("App isn't running, can't freeze the key!")
            return
        await self.config.execution_key.set(self.app.session.key.decode())
        await ctx.send(
            "Execution key frozen. Key will now remain the same between cog reloads."
        )

    @qupyterset.command(name="unfreezekey")
    async def qupyterset_unfreezekey(self, ctx: commands.Context) -> None:
        """
        Unfreeze the execution key used for signing messages.

        This ensures that the execution key will be chosen randomly at cog load.
        """
        await self.config.execution_key.set(None)
        await ctx.send(
            "Execution key unfrozen. Key will now be chosen randomly at cog load."
        )

    @qupyterset.command(name="setports")
    async def qupyterset_setports(
        self,
        ctx: commands.Context,
        shell_port: PortNumber,
        iopub_port: PortNumber,
        stdin_port: PortNumber,
        hb_port: PortNumber,
        control_port: PortNumber,
    ) -> None:
        """
        Set ports Qupyter's IPython kernel should run on.

        Ports are:
        `shell_port`   - The port the shell ROUTER socket is listening on.
        `iopub_port`   - The port the PUB socket is listening on.
        `stdin_port`   - The port the stdin ROUTER socket is listening on.
        `hb_port`      - The port the heartbeat socket is listening on.
        `control_port` - The port the control ROUTER socket is listening on.
        """
        await self.config.ports.set(
            [shell_port, iopub_port, stdin_port, hb_port, control_port]
        )
        await self.restart_app()
        await ctx.send("Ports set! Qupyter's IPython kernel has been restarted.")

    @qupyterset.command(name="clearports")
    async def qupyterset_clearports(self, ctx: commands.Context) -> None:
        """Clear set ports and use random selection of ports instead."""
        await self.config.ports.set(None)
        await self.restart_app()
        await ctx.send("Ports cleared! Qupyter's IPython kernel has been restarted.")

    @qupyterset.command(name="info")
    async def qupyterset_info(self, ctx: commands.Context) -> None:
        """Show information about running kernel."""
        port_msg = "\n".join(
            f"`{port_name}`: {getattr(self.app, port_name)}"
            for port_name in _PORT_NAMES
        )
        await ctx.send(
            f"Qupyter's IPython kernel is currently running on ports:\n{port_msg}"
        )
