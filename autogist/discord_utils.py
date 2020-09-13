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

from typing import TYPE_CHECKING, Optional, Tuple

import discord
from redbot.core.bot import Red

if TYPE_CHECKING:
    import chardet
else:
    try:
        import cchardet as chardet
    except ModuleNotFoundError:
        import chardet

from .log import log


# DEP-WARN
class RawMessage(discord.Message):
    """
    Raw message for doing API calls without fetching message first.

    Credit: Vex#3110 on Discord / Vexs on GitHub
    Modified for the usage in AutoGist cog.
    """

    def __init__(self, bot: Red, channel: discord.TextChannel, message_id: int) -> None:
        # pylint: disable=super-init-not-called
        self._state = bot._connection  # type: ignore[attr-defined]
        self.id = message_id
        self.channel = channel

    def __repr__(self) -> str:
        return f"<RawMessage id={self.id} channel={self.channel!r}>"


def can_edit_in_channel(channel: discord.TextChannel) -> bool:
    """
    Checks whether the bot has permissions to edit messages in the given channel.

    This function logs information about missing permissions.

    Returns
    -------
    bool
        `True` if bot can edit messages, `False` otherwise.
    """
    channel_perms = channel.permissions_for(channel.guild.me)
    if not channel_perms.read_message_history:
        log.debug("Bot can't read message history of channel with ID %s.", channel.id)
        return False
    if not channel_perms.send_messages:
        log.debug(
            "Bot can't send (and edit) messages in channel with ID %s.", channel.id
        )
        return False

    return True


async def safe_raw_edit(
    bot: Red, channel_id: int, message_id: int, *, content: str
) -> None:
    """
    Edits the message without raising.

    This function logs information about HTTP exceptions.
    """
    channel = bot.get_channel(channel_id)
    if channel is None:
        # that should not ever happen...
        log.warning("Channel with ID %s couldn't have been found.", channel_id)
        return
    assert isinstance(channel, discord.TextChannel)

    if not can_edit_in_channel(channel):
        return

    bot_message = RawMessage(bot, channel, message_id)

    try:
        await bot_message.edit(
            content=(
                "The original message with the file has been removed."
                " Gist with that file has been deleted for privacy reasons."
            )
        )
    except discord.NotFound:
        log.debug(
            "The message with ID %s-%s couldn't have been found.",
            channel_id,
            message_id,
        )
    except discord.Forbidden as e:
        log.info(
            "Bot was forbidden to edit message with ID %s-%s.",
            channel_id,
            message_id,
            exc_info=e,
        )
    except discord.HTTPException as e:
        log.error(
            "Unexpected error occurred when trying to edit message with ID %s-%s.",
            channel_id,
            message_id,
            exc_info=e,
        )


async def fetch_attachment_from_message(
    message: discord.Message,
) -> Tuple[str, Optional[str]]:
    """
    Fetches contents of first attachment from given message without raising.

    This function logs information about HTTP exceptions and decoding errors.

    Returns
    -------
    Tuple[str, Optional[str]]
        2-tuple of attachment filename and its content.
        Content (second value in tuple) will be `None`,
         if method fails to fetch or decode contents of the attachment.
    """
    attachment = message.attachments[0]
    content: Optional[str] = None

    try:
        raw_data = await attachment.read()
    except discord.HTTPException:
        log.info(
            "The attachment from message with ID %s-%s"
            " couldn't have been downloaded.",
            message.channel.id,
            message.id,
        )

    encoding_data = chardet.detect(raw_data)
    encoding = encoding_data["encoding"] or "utf-8"

    try:
        content = raw_data.decode(encoding)
    except UnicodeDecodeError:
        if encoding != "utf-8":
            try:
                content = raw_data.decode("utf-8")
            except UnicodeDecodeError:
                log.info(
                    "The contents of attachment from message with ID %s-%s"
                    " couldn't have been decoded using neither %s nor utf-8 encoding.",
                    message.channel.id,
                    message.id,
                    encoding,
                )
        else:
            log.info(
                "The contents of attachment from message with ID %s-%s"
                " couldn't have been decoded using utf-8 encoding.",
                message.channel.id,
                message.id,
            )

    return attachment.filename, content
