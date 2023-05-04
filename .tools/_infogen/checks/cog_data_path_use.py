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

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Literal

from .. import ROOT_PATH

if TYPE_CHECKING:
    from ..context import InfoGenMainCommand

__all__ = ("check_cog_data_path_use",)


def check_cog_data_path_use(ctx: InfoGenMainCommand) -> Literal[True]:
    for pkg_name in ctx.cogs:
        p = subprocess.run(
            ("git", "grep", "-q", "cog_data_path", "--", f"{pkg_name}/"),
            cwd=ROOT_PATH,
            check=False,
        )
        if p.returncode == 0:
            print(
                "\033[94m\033[1mINFO:\033[0m "
                f"{pkg_name} uses cog_data_path, make sure"
                " that you notify the user about it in install message."
            )
        elif p.returncode != 1:
            raise RuntimeError("git grep command failed")
    return True
