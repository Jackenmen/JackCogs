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

from pathlib import Path
from typing import TYPE_CHECKING, Literal

import parso

from .. import ROOT_PATH

if TYPE_CHECKING:
    from ..context import InfoGenMainCommand

__all__ = ("update_class_docstrings",)


def update_class_docstrings(ctx: InfoGenMainCommand) -> Literal[True]:
    """Update class docstrings with descriptions from info.yaml

    This is created with few assumptions:
    - name of cog's class is under "name" key in `cogs` dictionary
    - following imports until we find class definition is enough to find it
      - class name is imported directly:
      `from .rlstats import RLStats` not `from . import rlstats`
      - import is relative
      - star imports are ignored
    """
    for pkg_name, cog_info in ctx.cogs.items():
        # class_docstring: null is different from not passing it at all
        class_docstring = cog_info.get("class_docstring", ...)
        if class_docstring is None:
            continue
        new_docstring = cog_info["short"] if class_docstring is ... else class_docstring
        replacements = {
            "repo_name": ctx.repo_info["name"],
            "cog_name": cog_info["name"],
        }
        new_docstring = new_docstring.format_map(replacements)

        class_name = cog_info["name"]
        path = ROOT_PATH / pkg_name / "__init__.py"
        if not path.is_file():
            raise RuntimeError("Folder `{pkg_name}` isn't a valid package.")
        while True:
            source = ctx.results.get_file(path)
            tree = parso.parse(source)
            class_node = next(
                (
                    node
                    for node in tree.iter_classdefs()
                    if node.name.value == class_name
                ),
                None,
            )
            if class_node is not None:
                break

            new_path = None
            for import_node in tree.iter_imports():
                if import_node.is_star_import():
                    # we're ignoring star imports
                    continue
                for import_path in import_node.get_paths():
                    if import_path[-1].value == class_name:
                        break
                else:
                    continue

                if import_node.level == 0:
                    raise RuntimeError(
                        "Script expected relative import of cog's class."
                    )
                if import_node.level > 1:
                    raise RuntimeError(
                        "Attempted relative import beyond top-level package."
                    )
                new_path = ROOT_PATH / pkg_name
                for part in import_path[:-1]:
                    new_path /= part.value
                assert isinstance(new_path, Path)
                new_path = new_path.with_suffix(".py")
                if not path.is_file():
                    raise RuntimeError(
                        f"Path `{path}` isn't a valid file. Finding cog's class failed."
                    )
                break
            if new_path is None or path == new_path:
                print(
                    "\033[93m\033[1mWARNING:\033[0m "
                    f"Class for `{pkg_name}` cog package could not be found."
                )
                break
            path = new_path

        if class_node is None:
            continue
        doc_node = class_node.get_doc_node()
        if doc_node is not None:
            doc_node.value = f'"""{new_docstring}"""'
        else:
            first_leaf = class_node.children[-1].get_first_leaf()
            # gosh, this is horrible
            first_leaf.prefix = f'\n    """{new_docstring}"""\n'

        new_code = tree.get_code()
        if source != new_code:
            ctx.vprint(f"Updated class docstring for {class_name}")
            ctx.results.update_file(path, new_code)

    return True
