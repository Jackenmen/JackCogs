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
from redbot.core.commands import BadArgument
from redbot.core.utils.chat_formatting import humanize_number, inline

__all__ = ("PortNumber",)

if TYPE_CHECKING:
    PortNumber = int
else:

    class PortNumber(commands.Converter):
        async def convert(self, ctx: commands.Context, arg: str) -> int:
            try:
                ret = int(arg)
            except ValueError:
                raise BadArgument(f"{inline(arg)} is not an integer.")
            if ret < 1024:
                raise BadArgument("Privileged ports (<1024) can't be used.")
            if ret > 65_535:
                raise BadArgument(
                    f"Port number can't be higher than {humanize_number(65_535)}."
                )
            return ret
