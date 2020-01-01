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

    def __init__(self, *_args):
        self.loop: asyncio.AbstractEventLoop
        self._executor: ThreadPoolExecutor
        self.config: Config

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
