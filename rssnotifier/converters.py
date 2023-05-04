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

import contextlib
import re
from typing import TYPE_CHECKING, Union

import discord
from redbot.core import commands

__all__ = ("RawRoleObjectConverter",)


_id_regex = re.compile(r"([0-9]{15,21})$")
_mention_regex = re.compile(r"<@&([0-9]{15,21})>$")

_RawRole = Union[discord.Role, discord.Object]


if TYPE_CHECKING:
    RawRoleObjectConverter = _RawRole
else:

    class RawRoleObjectConverter(commands.RoleConverter):
        async def convert(self, ctx: commands.Context, arg: str) -> _RawRole:
            with contextlib.suppress(commands.BadArgument):
                return await super().convert(ctx, arg)

            if match := _id_regex.match(arg) or _mention_regex.match(arg):
                return discord.Object(int(match.group(1)))

            raise commands.BadArgument(f"Role '{arg}' not found.")
