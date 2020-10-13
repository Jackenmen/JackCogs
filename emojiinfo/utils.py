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

import re
import unicodedata
from typing import Generator, Pattern, Tuple

# mypy v0.790 was released with outdated typeshed...
from emoji import EMOJI_UNICODE  # type: ignore[attr-defined]

from .variations import EMOJIS_WITH_VARIATIONS

__all__ = ("EMOJI_REGEX", "get_emoji_repr", "iter_emojis")


def iter_emojis(raw_emojis: str) -> Generator[Tuple[str, str], None, None]:
    for match in EMOJI_REGEX.finditer(raw_emojis):
        emoji = match.group(0)
        if emoji[0] == "<":
            # custom emoji
            yield emoji, f"{emoji[:-1]}\\>"
            continue

        # unicode emoji
        yield emoji, f"`{get_emoji_repr(emoji)}`"


def get_emoji_repr(emoji: str) -> str:
    return "".join(
        get_char_repr(char)
        for char in emoji
        if char not in ("\N{VARIATION SELECTOR-15}", "\N{VARIATION SELECTOR-16}")
    )


def get_char_repr(char: str) -> str:
    char_repr = f"\\N{{{unicodedata.name(char)}}}"
    if char in EMOJIS_WITH_VARIATIONS:
        char_repr += "\\N{VARIATION SELECTOR-16}"
    return char_repr


def _generate_emoji_regex() -> Pattern[str]:
    # multi-char emojis need to take precedence
    emojis = sorted(EMOJI_UNICODE.values(), key=len, reverse=True)
    custom_emojis_pattern = r"(<a?:\w{2,32}:\d{18,22}>)"
    unicode_emojis_pattern = "|".join(re.escape(emoji) for emoji in emojis)
    return re.compile(f"{custom_emojis_pattern}|{unicode_emojis_pattern}")


EMOJI_REGEX = _generate_emoji_regex()
