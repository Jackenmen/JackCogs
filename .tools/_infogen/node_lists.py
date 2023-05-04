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

import parso

__all__ = (
    "CONTAINERS",
    "CONTAINERS_WITHOUT_LOCALS",
    "SMALL_STMT_LIST",
)

CONTAINERS = parso.python.tree._FUNC_CONTAINERS | {
    "async_funcdef",
    "funcdef",
    "classdef",
}

SMALL_STMT_LIST = {
    "expr_stmt",
    "del_stmt",
    "pass_stmt",
    "flow_stmt",
    "import_stmt",
    "global_stmt",
    "nonlocal_stmt",
    "assert_stmt",
}
CONTAINERS_WITHOUT_LOCALS = (
    parso.python.tree._RETURN_STMT_CONTAINERS
    | {"with_item"}
    | parso.python.tree._IMPORTS
    | SMALL_STMT_LIST
)
