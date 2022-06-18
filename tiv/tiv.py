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

from types import SimpleNamespace

import discord

from .delegate import delegate


def last_message_id(self: discord.VoiceChannel) -> None:
    return None


def get_partial_message(
    self: discord.VoiceChannel, message_id: int
) -> discord.PartialMessage:
    fake_obj = SimpleNamespace(
        type=discord.ChannelType.text, _state=getattr(self, "_state")
    )
    ret = discord.TextChannel.get_partial_message(
        fake_obj,  # type: ignore
        message_id,
    )
    ret.channel = self  # type: ignore
    return ret


DESCRIPTORS = [
    delegate(discord.abc.Messageable, "send"),
    delegate(discord.abc.Messageable, "trigger_typing"),
    delegate(discord.abc.Messageable, "typing"),
    delegate(discord.abc.Messageable, "fetch_message"),
    delegate(discord.abc.Messageable, "pins"),
    delegate(discord.abc.Messageable, "history"),
    delegate(discord.TextChannel, "_get_channel"),
    property(last_message_id),
    delegate(discord.TextChannel, "last_message"),
    get_partial_message,
    delegate(discord.TextChannel, "delete_messages"),
    delegate(discord.TextChannel, "purge"),
    delegate(discord.TextChannel, "webhooks"),
    delegate(discord.TextChannel, "create_webhook"),
]


def _tiv_load() -> None:
    for desc in DESCRIPTORS:
        setattr(discord.VoiceChannel, getattr(desc, "fget", desc).__name__, desc)


def _tiv_unload() -> None:
    for desc in DESCRIPTORS:
        delattr(discord.VoiceChannel, getattr(desc, "fget", desc).__name__)
