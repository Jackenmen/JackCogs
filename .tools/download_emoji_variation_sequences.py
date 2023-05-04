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

import textwrap
from pathlib import Path

import requests

ROOT_PATH = Path(__file__).parent.parent.absolute()
VARIATIONS_FILE = ROOT_PATH / "emojiinfo/variations.py"

r = requests.get(
    "https://www.unicode.org/Public/UCD/latest/ucd/emoji/emoji-variation-sequences.txt"
)
r.raise_for_status()

backslash_emoji_reprs = []

for line in r.text.splitlines():
    if not line or line.startswith("#"):
        continue
    variation_sequence = list(
        map(
            lambda x: chr(int(x, base=16)),
            line.split(";", maxsplit=1)[0].strip().split(),
        )
    )
    if variation_sequence[1] != "\N{VARIATION SELECTOR-16}":
        continue

    emoji = variation_sequence[0]
    backslash_repr = emoji.encode("ascii", "backslashreplace").decode("utf-8")
    backslash_emoji_reprs.append(backslash_repr)

inner_code = textwrap.indent(
    ",\n".join(f'"{backslash_repr}"' for backslash_repr in backslash_emoji_reprs),
    "    ",
)
code = f"EMOJIS_WITH_VARIATIONS = {{\n{inner_code},\n}}\n"

with VARIATIONS_FILE.open("w", encoding="utf-8", newline="\n") as fp:
    fp.write(code)
