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

import argparse
import shutil
import textwrap
from enum import Enum

__all__ = ("parser",)

# get_terminal_size can report 0, 0 if run from pseudo-terminal
# (https://bugs.python.org/issue42174)
_terminal_width = (shutil.get_terminal_size().columns or 80) - 2
_description = (
    textwrap.fill(
        "Script to automatically generate info.json files"
        " and generate class docstrings from single info.yaml file for whole repo.",
        _terminal_width,
    )
    + "\n\n"
    + textwrap.fill(
        "DISCLAIMER: While this script works, it uses some hacks"
        " and I don't recommend using it if you don't understand how it does some stuff"
        " and why it does it like this.",
        _terminal_width,
    )
)
parser = argparse.ArgumentParser(
    usage="%(prog)s [options]",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description=_description,
)
parser.add_argument(
    "--check",
    action="store_true",
    help="Don't write the files back, just return the status.",
)
parser.add_argument(
    "--diff",
    action="store_true",
    help="Don't write the files back, just output a diff for each file on stdout.",
)
parser.add_argument(
    "--verbose",
    "-v",
    action="store_true",
    help="Show verbose messages.",
)


# This class is basically copied from Black and changed for my use case.
class WriteBack(Enum):
    YES = 0
    DIFF = 1
    CHECK = 2

    @classmethod
    def from_configuration(cls, *, check: bool, diff: bool) -> WriteBack:
        if check and not diff:
            return cls.CHECK

        return cls.DIFF if diff else cls.YES


class Options:
    def __init__(self, write_back: WriteBack, verbose: bool) -> None:
        self.write_back = write_back
        self.verbose = verbose

    @classmethod
    def from_argv(cls) -> Options:
        args = parser.parse_args()
        return cls(
            write_back=WriteBack.from_configuration(check=args.check, diff=args.diff),
            verbose=args.verbose,
        )
