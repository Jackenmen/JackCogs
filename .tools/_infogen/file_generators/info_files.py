"""
Copyright 2018-2020 Jakub Kuczys (https://github.com/jack1142)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import json
import re
from types import SimpleNamespace
from typing import Dict, List, Literal, Set, Tuple

from redbot import VersionInfo

from .. import ROOT_PATH
from ..max_versions import MAX_PYTHON_VERSION, MAX_RED_VERSIONS
from ..schema import COG_KEYS_ORDER, KEYS_TO_SKIP_IN_COG_INFO
from ..typedefs import InfoYAMLDict, RepoInfoDict
from ..utils import safe_format_alt


def generate_repo_info_file(repo_info: RepoInfoDict) -> None:
    repo_info["install_msg"] = repo_info["install_msg"].format_map(
        {"repo_name": repo_info["name"]}
    )
    with open(ROOT_PATH / "info.json", "w", encoding="utf-8") as fp:
        json.dump(repo_info, fp, indent=4)


def process_cogs(data: InfoYAMLDict) -> bool:
    all_requirements: Set[str] = set()
    requirements: Dict[Tuple[int, int], Set[str]] = {
        (3, 8): set(),
    }
    black_file_list: Dict[Tuple[int, int], List[str]] = {
        (3, 8): [".ci"],
    }
    compileall_file_list: Dict[Tuple[int, int], List[str]] = {
        (3, 8): ["."],
    }
    repo_info = data["repo"]
    shared_fields = data["shared_fields"]
    global_min_bot_version = shared_fields.get("min_bot_version")
    global_min_python_version = shared_fields.get("min_python_version")
    cogs = data["cogs"]
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
        python_version = cog_info.get("min_python_version", global_min_python_version)
        if python_version is not None:
            if min_python_version < python_version:
                min_python_version = python_version
        for python_version, reqs in requirements.items():
            if python_version >= min_python_version:
                reqs.update(cog_info["requirements"])
        for python_version, file_list in compileall_file_list.items():
            if python_version == MAX_PYTHON_VERSION:
                continue
            if python_version >= min_python_version:
                file_list.append(pkg_name)
        black_file_list[min_python_version].append(pkg_name)

        print(f"Preparing info.json for {pkg_name} cog...")
        output = {}
        for key in COG_KEYS_ORDER:
            if key in KEYS_TO_SKIP_IN_COG_INFO:
                continue
            value = cog_info.get(key)
            if value is None:
                value = shared_fields.get(key)
                if value is None:
                    continue
            output[key] = value
        replacements = {
            "repo_name": repo_info["name"],
            "cog_name": output["name"],
        }
        shared_fields_namespace = SimpleNamespace(**shared_fields)
        maybe_bundled_data = ROOT_PATH / pkg_name / "data"
        if maybe_bundled_data.is_dir():
            new_msg = f"{output['install_msg']}\n\nThis cog comes with bundled data."
            output["install_msg"] = new_msg
        replacables: Tuple[Literal["short", "description", "install_msg"], ...] = (
            "short",
            "description",
            "install_msg",
        )
        for to_replace in replacables:
            output[to_replace] = safe_format_alt(
                output[to_replace], {"shared_fields": shared_fields_namespace}
            )
            if to_replace == "description":
                output[to_replace] = output[to_replace].format_map(
                    {**replacements, "short": output["short"]}
                )
            else:
                output[to_replace] = output[to_replace].format_map(replacements)

        with open(ROOT_PATH / pkg_name / "info.json", "w", encoding="utf-8") as fp:
            json.dump(output, fp, indent=4)

    print("Preparing requirements file for CI...")
    with open(ROOT_PATH / ".ci/requirements/all_cogs.txt", "w", encoding="utf-8") as fp:
        fp.write("Red-DiscordBot\n")
        for requirement in sorted(all_requirements):
            fp.write(f"{requirement}\n")
    for python_version, reqs in requirements.items():
        folder_name = f"py{''.join(map(str, python_version))}"
        with open(
            ROOT_PATH / f".ci/{folder_name}/requirements/all_cogs.txt",
            "w",
            encoding="utf-8",
        ) as fp:
            fp.write("Red-DiscordBot\n")
            for req in sorted(reqs):
                fp.write(f"{req}\n")
        with open(
            ROOT_PATH / f".ci/{folder_name}/black_file_list.txt", "w", encoding="utf-8"
        ) as fp:
            fp.write(" ".join(sorted(black_file_list[python_version])))
        with open(
            ROOT_PATH / f".ci/{folder_name}/compileall_file_list.txt",
            "w",
            encoding="utf-8",
        ) as fp:
            fp.write(" ".join(sorted(compileall_file_list[python_version])))

    print("Preparing all cogs list in README.md...")
    with open(ROOT_PATH / "README.md", "r+", encoding="utf-8") as fp:
        text = fp.read()
        match = re.search(
            r"# Cogs in this repo\n{2}(.+)\n{2}# Installation", text, flags=re.DOTALL
        )
        if match is None:
            print(
                "\033[91m\033[1mERROR:\033[0m Couldn't find cogs sections in README.md!"
            )
            return False
        start, end = match.span(1)
        lines = []
        for pkg_name, cog_info in cogs.items():
            replacements = {
                "repo_name": repo_info["name"],
                "cog_name": cog_info["name"],
            }
            desc = cog_info["short"].format_map(replacements)
            lines.append(f"* **{pkg_name}** - {desc}")
        cogs_section = "\n".join(lines)
        fp.seek(0)
        fp.truncate()
        fp.write(f"{text[:start]}{cogs_section}{text[end:]}")

    return True
