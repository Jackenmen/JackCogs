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
from ..node_lists import CONTAINERS
from ..utils import scan_recursively

if TYPE_CHECKING:
    from ..context import InfoGenMainCommand

__all__ = ("check_command_docstrings",)


def check_command_docstrings(ctx: InfoGenMainCommand) -> bool:
    success = True
    for pkg_name in ctx.cogs:
        pkg_folder = ROOT_PATH / pkg_name
        for file in pkg_folder.glob("**/*.py"):
            with file.open() as fp:
                tree = parso.parse(fp.read())
            for node in scan_recursively(tree.children, "async_funcdef", CONTAINERS):
                funcdef = node.children[-1]
                decorators = funcdef.get_decorators()
                ignore = False
                # DEP-WARN: use of private method
                for prefix_part in decorators[0].children[0]._split_prefix():
                    if (
                        prefix_part.type == "comment"
                        and prefix_part.value == "# geninfo-ignore: missing-docstring"
                    ):
                        ignore = True
                for deco in decorators:
                    maybe_name = deco.children[1]
                    if maybe_name.type == "dotted_name":
                        it = (n.value for n in maybe_name.children)
                        # ignore first item (can either be `commands` or `groupname`)
                        next(it, None)
                        deco_name = "".join(it)
                    elif maybe_name.type == "name":
                        deco_name = maybe_name.value
                    else:
                        raise RuntimeError("Unexpected type of decorator name.")
                    if deco_name in {".command", ".group"}:
                        break
                else:
                    continue
                if funcdef.get_doc_node() is None:
                    if not ignore:
                        print(
                            "\033[93m\033[1mWARNING:\033[0m "
                            f"command `{funcdef.name.value}` misses help docstring!"
                        )
                        success = False
                elif ignore:
                    print(
                        "\033[93m\033[1mWARNING:\033[0m "
                        f"command `{funcdef.name.value}` has unused"
                        " missing-docstring ignore comment!"
                    )
                    success = False
    return success
