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

from typing import TYPE_CHECKING

from redbot.core import commands
from redbot.core.commands import GuildContext
from redbot.core.utils.common_filters import URL_RE

if TYPE_CHECKING:
    DomainName = str
else:

    class DomainName(commands.Converter):
        async def convert(self, ctx: GuildContext, argument: str) -> str:
            if (match := URL_RE.search(argument)) is not None:
                raise commands.BadArgument(
                    f"It looks like you're trying to add a full URL (<{argument}>)"
                    f" rather than just the domain name ({match.group(2)}).\n"
                    "Please try again with just the domain name."
                )
            return argument
