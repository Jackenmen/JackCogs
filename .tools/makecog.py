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

import sys

LICENSE_HEADER = """
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
""".strip()

INIT_FILE_TEMPLATE = f"""
{LICENSE_HEADER}

import json
from pathlib import Path

from redbot.core.bot import Red

from .{{package_name}} import {{name}}

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


async def setup(bot: Red) -> None:
    cog = {{name}}(bot)
    bot.add_cog(cog)
""".lstrip()

CORE_FILE_TEMPLATE = f'''
{LICENSE_HEADER}

from typing import Any, Dict, Literal

from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.config import Config

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]


class {{name}}(commands.Cog):
    """{{class_docstring}}"""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, 176070082584248320, force_registration=True)

    async def red_get_data_for_user(self, *, user_id: int) -> Dict[str, Any]:
        # TODO: Replace this with the proper end user data handling.
        super().red_get_data_for_user(user_id=user_id)

    async def red_delete_data_for_user(
        self, *, requester: RequestType, user_id: int
    ) -> None:
        # TODO: Replace this with the proper end user data handling.
        super().red_delete_data_for_user(requester=requester, user_id=user_id)
'''.lstrip()


def main() -> bool:
    ...


if __name__ == "__main__":
    sys.exit(int(not main()))
