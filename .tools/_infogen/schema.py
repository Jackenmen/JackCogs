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

from typing import cast

from strictyaml import (
    Bool,
    EmptyDict,
    EmptyList,
    Enum,
    Map,
    MapPattern,
    NullNone,
    Optional,
    Seq,
    Str,
    Url,
    load as yaml_load,
)

from . import ROOT_PATH
from .schema_validators import PythonVersion, RedVersion
from .typedefs import InfoYAMLDict

__all__ = (
    # Metadata keys.
    "COG_KEYS",
    "COMMON_KEYS",
    "REPO_KEYS",
    "SHARED_FIELDS_KEYS",
    # Schema.
    "SCHEMA",
    # Keys to skip.
    "KEYS_TO_SKIP_IN_COG_INFO",
    # Key order.
    "COG_KEYS_ORDER",
    "REPO_KEYS_ORDER",
    "SHARED_FIELDS_KEYS_ORDER",
)

#: `repo` metadata keys.
REPO_KEYS = {
    "name": Str(),  # Downloader doesn't use this, but cogs.red might.
    "short": Str(),
    "description": Str(),
    "install_msg": Str(),
    "author": Seq(Str()),
}

#: Metadata keys common to `shared_fields` and `cogs` schemas.
COMMON_KEYS = {
    Optional("min_bot_version"): RedVersion(),
    Optional("max_bot_version"): RedVersion(),
    Optional("min_python_version"): PythonVersion(),
    Optional("hidden", False): Bool(),
    Optional("disabled", False): Bool(),
    Optional("type", "COG"): Enum(["COG", "SHARED_LIBRARY"]),
}

#: `shared_fields` metadata keys.
SHARED_FIELDS_KEYS = {
    "install_msg": Str(),
    "author": Seq(Str()),
    **COMMON_KEYS,
}

#: `cogs` metadata keys.
COG_KEYS = {
    "name": Str(),  # Downloader doesn't use this but I can set friendlier name
    "short": Str(),
    "description": Str(),
    "end_user_data_statement": Str(),
    Optional("class_docstring"): NullNone() | Str(),
    Optional("install_msg"): Str(),
    Optional("author"): Seq(Str()),
    Optional("required_cogs", {}): EmptyDict() | MapPattern(Str(), Url()),
    Optional("requirements", []): EmptyList() | Seq(Str()),
    Optional("tags", []): EmptyList() | Seq(Str()),
    **COMMON_KEYS,
}

#: Root schema of the info.yaml file.
SCHEMA = Map(
    {
        "repo": Map(REPO_KEYS),
        "shared_fields": Map(SHARED_FIELDS_KEYS),
        "cogs": MapPattern(Str(), Map(COG_KEYS)),
    }
)

#: Keys that should be skipped when outputting to info.json.
#: These keys are for infogen's usage.
KEYS_TO_SKIP_IN_COG_INFO = {"class_docstring"}

#: Order the keys in `cogs` section of info.yaml should be in.
COG_KEYS_ORDER = list(getattr(key, "key", key) for key in COG_KEYS)

#: Order the keys in `repo` section of info.yaml should be in.
REPO_KEYS_ORDER = list(REPO_KEYS.keys())

#: Order the keys in `shared_fields` section of info.yaml should be in.
SHARED_FIELDS_KEYS_ORDER = list(getattr(key, "key", key) for key in SHARED_FIELDS_KEYS)


def load_info_yaml() -> InfoYAMLDict:
    """
    Load info.yaml file from the root of the repository.

    Raises
    ------
    YAMLValidationError
        When there was an error during schema validation of the info.yaml file.

    Returns
    -------
    YAML
        YAML data of the info.yaml file.
    """
    with open(ROOT_PATH / "info.yaml", encoding="utf-8") as fp:
        data = yaml_load(fp.read(), SCHEMA, label="info.yaml").data
        # the proper dictionary is already ensured by StrictYAML
        return cast(InfoYAMLDict, data)
