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
import asyncio.subprocess as asp
import os
import re
import sys
from typing import Dict

from redbot.core import commands
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.utils.menus import menu

from .errors import ProcessTerminatedEarly

__all__ = ("get_env", "send_pages", "strip_code_block", "wait_for_result")

START_CODE_BLOCK_RE = re.compile(r"^((```.*)(?=\s)|(```))")


def get_env() -> Dict[str, str]:
    env = os.environ.copy()
    if hasattr(sys, "real_prefix") or sys.base_prefix != sys.prefix:
        # os.path.sep - this is folder separator, i.e. `\` on win or `/` on unix
        # os.pathsep - this is paths separator in PATH, i.e. `;` on win or `:` on unix
        # a wonderful idea to call them almost the same >.<
        if sys.platform == "win32":
            binfolder = f"{sys.prefix}{os.path.sep}Scripts"
            env["PATH"] = f"{binfolder}{os.pathsep}{env['PATH']}"
        else:
            binfolder = f"{sys.prefix}{os.path.sep}bin"
            env["PATH"] = f"{binfolder}{os.pathsep}{env['PATH']}"
    return env


async def _reader(process: asp.Process) -> str:
    # it's all buffered in memory, so let's hope nobody will use this
    # with incredibly big output
    lines = []
    assert process.stdout is not None
    try:
        async for line in process.stdout:
            lines.append(line)
    except asyncio.CancelledError:
        # this is a bit of an abuse,
        # but cancelling helps nicely with controlling the flow
        raise ProcessTerminatedEarly(lines) from None
    return b"".join(lines).decode("utf-8", "replace")


async def wait_for_result(process: asp.Process) -> str:
    """
    Wait for result from given process and return its output.

    Raises
    ------
    ProcessTerminatedEarly
        When given process gets killed early.
    """
    task = asyncio.create_task(_reader(process))
    try:
        await process.wait()
    except asyncio.CancelledError:
        # we don't want the task to keep waiting if something cancels waiting
        task.cancel()
        raise
    try:
        return await asyncio.wait_for(task, timeout=1)
    except asyncio.TimeoutError:
        task.cancel()
    return await task


async def send_pages(
    ctx: commands.Context, *, command: str, output: str, prefix: str = ""
) -> None:
    output_parts = list(pagify(output, shorten_by=len(prefix) + len(command) + 100))
    command_box = box(command)
    if not output_parts:
        output_parts = ["Command didn't return anything."]
    total_pages = len(output_parts)
    pages = [
        f"{prefix}Page {idx}/{total_pages} of output of shell command:\n"
        f"{command_box}\n{box(part, lang='ansi')}"
        for idx, part in enumerate(output_parts, 1)
    ]
    await menu(ctx, pages)


def strip_code_block(command: str) -> str:
    if command.startswith("```") and command.endswith("```"):
        return START_CODE_BLOCK_RE.sub("", command)[:-3]
    return command
