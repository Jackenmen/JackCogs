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

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from types import TracebackType
from typing import Optional, Type, TypeVar

import discord
import discord.context_managers
from redbot.core.bot import Red

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]

log = logging.getLogger("red.jackcogs.patchtyping")

original_trigger_typing = discord.abc.Messageable.trigger_typing
original_typing = discord.abc.Messageable.typing


def setup(bot: Red) -> None:
    if discord.version_info >= (1, 7, 4):
        raise RuntimeError("unsupported discord.py version")
    discord.abc.Messageable.trigger_typing = trigger_typing  # type: ignore
    discord.abc.Messageable.typing = typing  # type: ignore


def teardown(bot: Red) -> None:
    discord.abc.Messageable.trigger_typing = original_trigger_typing  # type: ignore
    discord.abc.Messageable.typing = original_typing  # type: ignore


async def trigger_typing(self: discord.abc.Messageable) -> None:
    channel = await self._get_channel()  # type: ignore[attr-defined]
    try:
        await self._state.http.send_typing(channel.id)  # type: ignore[attr-defined]
    except discord.HTTPException:
        log.info(
            "Discord API has returned an improper response"
            " in channel typing endpoint, ignoring..."
        )


def typing(self: discord.abc.Messageable) -> Typing:
    return Typing(self)


trigger_typing.__doc__ = original_trigger_typing.__doc__
typing.__doc__ = original_typing.__doc__


TypingT = TypeVar("TypingT", bound="Typing")


class Typing(discord.context_managers.Typing):
    def __init__(self, messageable: discord.abc.Messageable) -> None:
        self.messageable = messageable
        self.task = None

    async def do_typing(self) -> None:
        try:
            channel = self._channel
        except AttributeError:
            channel = await self.messageable._get_channel()  # type: ignore

        typing = channel._state.http.send_typing

        while True:
            await typing(channel.id)
            await asyncio.sleep(5)

    def __enter__(self: TypingT) -> TypingT:
        self.task = asyncio.create_task(self.do_typing())
        self.task.add_done_callback(_typing_done_callback)
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        if self.task is not None:
            self.task.cancel()

    async def __aenter__(self: TypingT) -> TypingT:
        self._channel = channel = await self.messageable._get_channel()  # type: ignore
        try:
            await channel._state.http.send_typing(channel.id)
        except discord.HTTPException:
            log.info(
                "Discord API has returned an improper response"
                " in channel typing endpoint, ignoring..."
            )
            return self
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        if self.task is not None:
            self.task.cancel()


def _typing_done_callback(fut: asyncio.Future) -> None:  # type: ignore[type-arg]
    # just retrieve any exception and call it a day
    try:
        fut.exception()
    except (asyncio.CancelledError, Exception):
        pass
