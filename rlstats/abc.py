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

import asyncio
from abc import ABC, ABCMeta, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, TypeVar

import rlapi
from discord.ext.commands import CogMeta
from redbot.core.config import Config

from .image import RLStatsImageTemplate

T = TypeVar("T")


class CogAndABCMeta(CogMeta, ABCMeta):
    """
    This allows the metaclass used for proper type detection to
    coexist with discord.py's metaclass.
    """


class MixinMeta(ABC):
    """Base class for well behaved type hint detection with composite class."""

    def __init__(self, *_args: Any) -> None:
        self.loop: asyncio.AbstractEventLoop
        self._executor: ThreadPoolExecutor
        self.config: Config

        self.breakdown_lock: asyncio.Lock
        self.breakdown_updated_at: float
        self.rlapi_client: rlapi.Client
        self.cog_data_path: Path
        self.bundled_data_path: Path
        self.competitive_template: RLStatsImageTemplate
        self.extramodes_template: RLStatsImageTemplate

    @abstractmethod
    async def _run_in_executor(
        self, func: Callable[..., T], *args: Any, **kwargs: Any
    ) -> T:
        raise NotImplementedError()
