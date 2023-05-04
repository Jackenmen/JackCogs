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

"""
This an incomplete stub of IPython library for use of cogs in this repo.
Nobody have made a full stub for this library so only stuff used by this repo is typed.
"""

import abc
from types import FrameType
from typing import Any, Dict, Optional

from traitlets.config.configurable import SingletonConfigurable

from .async_helpers import _asyncio_runner as _asyncio_runner, _AsyncIORunner
from .events import EventManager
from .payload import PayloadManager

class ExecutionResult: ...

class InteractiveShell(SingletonConfigurable):
    execution_count: int
    events: EventManager
    loop_runner: _AsyncIORunner
    payload_manager: PayloadManager
    def set_completer_frame(self, frame: Optional[FrameType] = None) -> None: ...
    def run_cell(
        self,
        raw_cell: str,
        store_history: bool = False,
        silent: bool = False,
        shell_futures: bool = True,
    ) -> ExecutionResult: ...
    async def run_cell_async(
        self,
        raw_cell: str,
        store_history: bool = False,
        silent: bool = False,
        shell_futures: bool = True,
        *,
        transformed_cell: Optional[str] = None,
        preprocessing_exc_tuple: Optional[Any] = None,
    ) -> ExecutionResult: ...
    def should_run_async(
        self,
        raw_cell: str,
        *,
        transformed_cell: Optional[str] = None,
        preprocessing_exc_tuple: Optional[Any] = None,
    ) -> bool: ...
    def user_expressions(self, expressions: Dict[str, str]) -> Dict[str, Any]: ...
