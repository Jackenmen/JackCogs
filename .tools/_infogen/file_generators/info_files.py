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

import json
import re
from types import SimpleNamespace
from typing import TYPE_CHECKING, Dict, List, Literal, Set, Tuple, cast

from redbot import VersionInfo

from .. import ROOT_PATH
from ..max_versions import MAX_PYTHON_VERSION, MAX_RED_VERSIONS
from ..schema import COG_KEYS_ORDER, KEYS_TO_SKIP_IN_COG_INFO
from ..typedefs import CogInfoDict
from ..utils import safe_format_alt

if TYPE_CHECKING:
    from ..context import InfoGenMainCommand

__all__ = ("generate_repo_info_file", "process_cogs")


def generate_repo_info_file(ctx: InfoGenMainCommand) -> Literal[True]:
    repo_info = ctx.repo_info
    repo_info["install_msg"] = repo_info["install_msg"].format_map(
        {"repo_name": repo_info["name"]}
    )
    ctx.results.update_file(ROOT_PATH / "info.json", json.dumps(repo_info, indent=4))

    return True


def process_cogs(ctx: InfoGenMainCommand) -> bool:
    success = True
    all_requirements: Set[str] = set()
    requirements: Dict[Tuple[int, int], Set[str]] = {
        (3, 8): set(),
    }
    black_file_list: Dict[Tuple[int, int], List[str]] = {
        (3, 8): [".ci", ".stubs", ".tools"],
    }
    compileall_file_list: Dict[Tuple[int, int], List[str]] = {
        (3, 8): ["."],
    }
    repo_info = ctx.repo_info
    shared_fields = ctx.shared_fields
    global_min_bot_version = shared_fields.get("min_bot_version")
    global_min_python_version = shared_fields.get("min_python_version")
    cogs = ctx.cogs
    for pkg_name, cog_info in cogs.items():
        all_requirements.update(cog_info["requirements"])
        min_bot_version = cog_info.get("min_bot_version", global_min_bot_version)
        min_python_version = (3, 8)
        if min_bot_version is not None:
            red_version_info = VersionInfo.from_str(min_bot_version)
            for python_version, max_red_version in MAX_RED_VERSIONS.items():
                if max_red_version is None:
                    min_python_version = python_version
                    break
                if red_version_info >= max_red_version:
                    continue
                min_python_version = python_version
                break
        maybe_python_version = cog_info.get(
            "min_python_version", global_min_python_version
        )
        if maybe_python_version is not None:
            if min_python_version < maybe_python_version:
                min_python_version = maybe_python_version[:2]
        for python_version, reqs in requirements.items():
            if python_version >= min_python_version:
                reqs.update(cog_info["requirements"])
        for python_version, file_list in compileall_file_list.items():
            if python_version == MAX_PYTHON_VERSION:
                continue
            if python_version >= min_python_version:
                file_list.append(pkg_name)
        black_file_list[min_python_version].append(pkg_name)

        ctx.vprint(f"Preparing info.json for {pkg_name} cog...")
        _output = {}
        for key in COG_KEYS_ORDER:
            if key in KEYS_TO_SKIP_IN_COG_INFO:
                continue
            value = cog_info.get(key)
            if value is None:
                value = shared_fields.get(key)
                if value is None:
                    continue
            _output[key] = value
        output = cast(CogInfoDict, _output)
        replacements = {
            "repo_name": repo_info["name"],
            "cog_name": output["name"],
        }
        shared_fields_namespace = SimpleNamespace(**shared_fields)
        maybe_bundled_data = ROOT_PATH / pkg_name / "data"
        if maybe_bundled_data.is_dir():
            new_msg = f"{output['install_msg']}\n\nThis cog comes with bundled data."
            output["install_msg"] = new_msg
        replaceables: Tuple[Literal["short", "description", "install_msg"], ...] = (
            "short",
            "description",
            "install_msg",
        )
        for to_replace in replaceables:
            output[to_replace] = safe_format_alt(
                output[to_replace], {"shared_fields": shared_fields_namespace}
            )
            if to_replace == "description":
                output[to_replace] = output[to_replace].format_map(
                    {**replacements, "short": output["short"]}
                )
            else:
                output[to_replace] = output[to_replace].format_map(replacements)

        ctx.results.update_file(
            ROOT_PATH / pkg_name / "info.json", json.dumps(output, indent=4)
        )

    ctx.vprint("Preparing requirements files for CI...")
    success &= _generate_requirements_files(
        ctx, all_requirements, requirements, black_file_list, compileall_file_list
    )

    ctx.vprint("Preparing all cogs list in README.md...")
    success &= _update_readme(ctx)

    return success


def _generate_requirements_files(
    ctx: InfoGenMainCommand,
    all_requirements: Set[str],
    requirements: Dict[Tuple[int, int], Set[str]],
    black_file_list: Dict[Tuple[int, int], List[str]],
    compileall_file_list: Dict[Tuple[int, int], List[str]],
) -> Literal[True]:
    # TODO: This needs to be refactored
    results = ctx.results

    contents = "Red-DiscordBot\n"
    contents += "".join(f"{requirement}\n" for requirement in sorted(all_requirements))
    results.update_file(ROOT_PATH / ".ci/requirements/all_cogs.txt", contents)

    for python_version, reqs in requirements.items():
        folder_name = f"py{''.join(map(str, python_version))}"

        contents = "Red-DiscordBot\n"
        contents += "".join(f"{req}\n" for req in sorted(reqs))
        results.update_file(
            ROOT_PATH / f".ci/{folder_name}/requirements/all_cogs.txt", contents
        )

        results.update_file(
            ROOT_PATH / f".ci/{folder_name}/black_file_list.txt",
            " ".join(sorted(black_file_list[python_version])),
        )

        results.update_file(
            ROOT_PATH / f".ci/{folder_name}/compileall_file_list.txt",
            " ".join(sorted(compileall_file_list[python_version])),
        )

    return True


def _update_readme(ctx: InfoGenMainCommand) -> bool:
    path = ROOT_PATH / "README.md"
    text = ctx.results.get_file(path)

    match = re.search(
        r"# Cogs in this repo\n{2}(.+)\n{2}# Installation", text, flags=re.DOTALL
    )
    if match is None:
        print("\033[91m\033[1mERROR:\033[0m Couldn't find cogs sections in README.md!")
        return False
    start, end = match.span(1)
    lines = []
    for pkg_name, cog_info in ctx.cogs.items():
        if cog_info["disabled"] or cog_info["hidden"]:
            continue
        replacements = {
            "repo_name": ctx.repo_info["name"],
            "cog_name": cog_info["name"],
        }
        desc = cog_info["short"].format_map(replacements)
        lines.append(f"* **{pkg_name}** - {desc}")
    cogs_section = "\n".join(lines)

    ctx.results.update_file(path, f"{text[:start]}{cogs_section}{text[end:]}")

    return True
