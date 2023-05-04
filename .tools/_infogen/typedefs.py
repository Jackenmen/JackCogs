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

from typing import Dict, List, Literal, Optional, Tuple, TypedDict

__all__ = (
    "CogsDict",
    "CogInfoDict",
    "InfoYAMLDict",
    "RepoInfoDict",
    "SharedFieldsDict",
)


class InfoYAMLDict(TypedDict):
    repo: RepoInfoDict
    shared_fields: SharedFieldsDict
    cogs: CogsDict


class RepoInfoDict(TypedDict):
    name: str
    short: str
    description: str
    install_msg: str
    author: List[str]


class _CommonOptionalKeys(TypedDict, total=False):
    min_bot_version: str
    max_bot_version: str
    min_python_version: Tuple[int, int, int]
    hidden: bool
    disabled: bool
    type: Literal["COG", "SHARED_LIBRARY"]


class SharedFieldsDict(_CommonOptionalKeys, total=True):
    install_msg: str
    author: List[str]


class _OptionalCogKeys(_CommonOptionalKeys, total=False):
    class_docstring: Optional[str]
    install_msg: str
    author: List[str]


class CogInfoDict(_OptionalCogKeys, total=True):
    name: str
    short: str
    description: str
    end_user_data_statement: str
    # the keys below have defined default values in the schema
    required_cogs: Dict[str, str]
    requirements: List[str]
    tags: List[str]


CogsDict = Dict[str, CogInfoDict]
