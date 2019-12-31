from abc import ABC, ABCMeta
from pathlib import Path

import rlapi

from discord.ext.commands import CogMeta
from redbot.core.config import Config
from .image import RLStatsImageTemplate


class CogAndABCMeta(CogMeta, ABCMeta):
    """
    This allows the metaclass used for proper type detection to
    coexist with discord.py's metaclass.
    """


class MixinMeta(ABC):
    """Base class for well behaved type hint detection with composite class."""

    def __init__(self, *_args):
        self.rlapi_client: rlapi.Client
        self.config: Config
        self.cog_data_path: Path
        self.bundled_data_path: Path
        self.competitive_template: RLStatsImageTemplate
        self.extramodes_template: RLStatsImageTemplate
