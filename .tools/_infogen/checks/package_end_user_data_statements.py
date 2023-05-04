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

from typing import TYPE_CHECKING

import parso

from .. import ROOT_PATH
from ..node_lists import CONTAINERS_WITHOUT_LOCALS
from ..utils import scan_recursively

if TYPE_CHECKING:
    from ..context import InfoGenMainCommand

__all__ = ("check_package_end_user_data_statements",)


def check_package_end_user_data_statements(ctx: InfoGenMainCommand) -> bool:
    success = True
    for pkg_name, cog_info in ctx.cogs.items():
        path = ROOT_PATH / pkg_name / "__init__.py"
        if not path.is_file():
            raise RuntimeError("Folder `{pkg_name}` isn't a valid package.")
        with path.open(encoding="utf-8") as fp:
            source = fp.read()
        tree = parso.parse(source)
        for node in scan_recursively(tree.children, "name", CONTAINERS_WITHOUT_LOCALS):
            if node.value == "__red_end_user_data_statement__":
                break
        else:
            print(
                "\033[93m\033[1mWARNING:\033[0m "
                f"cog package `{pkg_name}` is missing end user data statement!"
            )
            success = False

    return success
