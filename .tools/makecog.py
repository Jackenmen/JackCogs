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
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

import yaml
from prompt_toolkit import HTML, print_formatted_text

from _cli_utils import (
    GoToLast,
    GoToNext,
    GoToPrevious,
    PackageNameValidator,
    PythonIdentifierValidator,
    TagsValidator,
    dialoglist,
    not_empty,
    prompt,
)

ROOT_PATH = Path(__file__).absolute().parent.parent

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

from .{{pkg_name}} import {{name}}

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


def ask_for_class_name(data: Dict[str, Any], *, allow_next: bool = False) -> None:
    data["name"] = prompt(
        "Class name: ",
        validator=PythonIdentifierValidator(),
        allow_previous=False,
        allow_next=allow_next,
    )


def ask_for_pkg_name(data: Dict[str, Any], *, allow_next: bool = False) -> None:
    data["pkg_name"] = prompt(
        "Package name: ",
        default=data["name"].lower(),
        validator=PackageNameValidator(),
        allow_next=allow_next,
    )


def ask_for_short(data: Dict[str, Any], *, allow_next: bool = False) -> None:
    data["short"] = prompt(
        "Short description: ",
        allow_next=allow_next,
    )


def ask_for_description(data: Dict[str, Any], *, allow_next: bool = False) -> None:
    data["description"] = prompt(
        "Long description: ",
        default="{short}",
        multiline=True,
        allow_next=allow_next,
    )


def ask_for_end_user_data_statement(data: Dict[str, Any], *, allow_next: bool = False) -> None:
    data["end_user_data_statement"] = prompt(
        "End user data statement: ",
        default="This cog does not persistently store data or metadata about users.",
        multiline=True,
        allow_next=allow_next,
    )


def ask_for_class_docstring(data: Dict[str, Any], *, allow_next: bool = False) -> None:
    val = prompt(
        "Class docstring: ",
        validator=None,
        allow_next=allow_next,
    )
    if val:
        data["class_docstring"] = val


def ask_for_install_msg(data: Dict[str, Any], *, allow_next: bool = False) -> None:
    val = prompt(
        "Install message: ",
        validator=None,
        multiline=True,
        allow_next=allow_next,
    )
    if val:
        data["install_msg"] = val


def ask_for_tags(data: Dict[str, Any], *, allow_next: bool = False) -> None:
    data["tags"] = prompt(
        "Tags (separate with space): ",
        default="",
        validator=TagsValidator(),
        allow_next=allow_next,
    ).split()


def ask_for_confirmation(data: Dict[str, Any], *, allow_next: bool = False) -> None:
    print("---")
    tags_list = "\n".join(f"- {tag}" for tag in data["tags"])
    text = HTML(
        f"<u>Class name</u>\n{data['name']}\n"
        f"<u>Package name</u>\n{data['pkg_name']}\n"
        f"<u>Short description</u>\n{data['short']}\n"
        f"<u>Description</u>\n{data['description']}\n"
        f"<u>End user data statement</u>\n{data['end_user_data_statement']}\n"
        f"<u>Install message</u>\n{data.get('install_msg', 'Default')}\n"
        f"<u>Tags</u>\n{tags_list}\n"
    )
    print_formatted_text(text)
    dialoglist(
        "Is everything correct?",
        [(True, "Yes")],
        multi_choice=True,
        show_scrollbar=False,
        exit_condition=not_empty,
    )


if TYPE_CHECKING:
    # just put one of the functions so it can infer the correct callable type
    QUESTIONS = [ask_for_class_name]
else:
    QUESTIONS = [
        value
        for var_name, value in globals().items()
        if var_name.startswith("ask_for_")
    ]


def make_cog_from_data(data: Dict[str, Any]) -> None:
    pkg_name = data["pkg_name"]
    name = data["name"]
    class_docstring = data.get("class_docstring") or data["short"]
    pkg_dir = ROOT_PATH / pkg_name
    pkg_dir.mkdir()
    with open(pkg_dir / "__init__.py", "w", encoding="utf-8") as fp:
        fp.write(INIT_FILE_TEMPLATE.format(pkg_name=pkg_name, name=name))
    with open(pkg_dir / f"{pkg_name}.py", "w", encoding="utf-8") as fp:
        fp.write(CORE_FILE_TEMPLATE.format(name=name, class_docstring=class_docstring))
    yaml_data = {
        pkg_name: {
            "name": name,
            "short": data["short"],
            "description": data["description"],
            "end_user_data_statement": data["end_user_data_statement"],
            "tags": data["tags"],
        }
    }
    if (class_docstring := data.get("class_docstring")) is not None:
        yaml_data["class_docstring"] = class_docstring
    if (install_msg := data.get("install_msg")) is not None:
        yaml_data["install_msg"] = install_msg
    print_formatted_text(HTML("\n<u>YAML data</u>"))
    print(yaml.dump(yaml_data))


def main() -> bool:
    print(
        "Make a new cog | JackCogs\n"
        "-------------------------\n"
    )
    data: Dict[str, Any] = {}
    idx = 0
    max_idx = 0
    questions_count = len(QUESTIONS)
    while idx < questions_count:
        question = QUESTIONS[idx]
        try:
            question(data, allow_next=idx < max_idx)
        except GoToPrevious:
            idx -= 1
        except GoToNext:
            idx += 1
        except GoToLast:
            idx = max_idx
        else:
            idx += 1
            max_idx += 1

    make_cog_from_data(data)

    return True


if __name__ == "__main__":
    try:
        sys.exit(int(not main()))
    except KeyboardInterrupt:
        print("Aborting!")
