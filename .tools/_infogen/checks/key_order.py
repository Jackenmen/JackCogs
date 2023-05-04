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

from typing import TYPE_CHECKING, Dict, List, Literal, Tuple

from ..schema import COG_KEYS_ORDER, REPO_KEYS_ORDER, SHARED_FIELDS_KEYS_ORDER
from ..typedefs import CogInfoDict

if TYPE_CHECKING:
    from ..context import InfoGenMainCommand

__all__ = ("check_key_order",)


def check_key_order(ctx: InfoGenMainCommand) -> bool:
    """Temporary order checking, until strictyaml adds proper support for sorting."""
    success = True
    success &= _check_repo_info_and_shared_fields_key_order(ctx)
    success &= _check_cog_names_alphaorder(ctx)
    success &= _check_cog_info_key_order(ctx)

    return success


def _check_repo_info_and_shared_fields_key_order(ctx: InfoGenMainCommand) -> bool:
    to_check: Dict[Literal["repo", "shared_fields"], List[str]] = {
        "repo": REPO_KEYS_ORDER,
        "shared_fields": SHARED_FIELDS_KEYS_ORDER,
    }
    success = True
    for key, order in to_check.items():
        section = ctx.data[key]
        original_keys = list(section.keys())
        sorted_keys = sorted(section.keys(), key=order.index)
        if original_keys != sorted_keys:
            print(
                "\033[93m\033[1mWARNING:\033[0m "
                f"Keys in `{key}` section have wrong order - use this order: "
                f"{', '.join(sorted_keys)}"
            )
            success = False

    return success


def _check_cog_names_alphaorder(ctx: InfoGenMainCommand) -> bool:
    original_cog_names = list(ctx.cogs.keys())
    sorted_cog_names = sorted(ctx.cogs.keys())
    if original_cog_names != sorted_cog_names:
        print(
            "\033[93m\033[1mWARNING:\033[0m "
            "Cog names in `cogs` section aren't sorted. Use alphabetical order."
        )
        return False

    return True


def _check_cog_info_key_order(ctx: InfoGenMainCommand) -> bool:
    success = True
    for pkg_name, cog_info in ctx.cogs.items():
        # strictyaml breaks ordering of keys for optionals with default values
        original_keys = list((k for k, v in cog_info.items() if v))
        sorted_keys = sorted(
            (k for k, v in cog_info.items() if v), key=COG_KEYS_ORDER.index
        )
        if original_keys != sorted_keys:
            print(
                "\033[93m\033[1mWARNING:\033[0m "
                f"Keys in `cogs->{pkg_name}` section have wrong order"
                f" - use this order: {', '.join(sorted_keys)}"
            )
            print(original_keys)
            print(sorted_keys)
            success = False

        success &= _check_cog_info_collections_alphaorder(pkg_name, cog_info)

    return success


def _check_cog_info_collections_alphaorder(
    pkg_name: str, cog_info: CogInfoDict
) -> bool:
    collections: Tuple[Literal["required_cogs", "requirements", "tags"], ...] = (
        "required_cogs",
        "requirements",
        "tags",
    )
    success = True
    for key in collections:
        list_or_dict = cog_info[key]
        if isinstance(list_or_dict, dict):
            original_list = list(list_or_dict.keys())
        else:
            original_list = list_or_dict
        sorted_list = sorted(original_list)
        if original_list != sorted_list:
            friendly_name = key.capitalize().replace("_", " ")
            print(
                "\033[93m\033[1mWARNING:\033[0m "
                f"{friendly_name} for `{pkg_name}` cog aren't sorted."
                " Use alphabetical order."
            )
            print(original_list)
            print(sorted_list)
            success = False

    return success
