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

import difflib
from pathlib import Path
from typing import Dict, Generator, Optional

from . import ROOT_PATH
from .cli import Options, WriteBack


class FileInfo:
    def __init__(self, path: Path, src_contents: str) -> None:
        self.path = path
        self.src_contents = src_contents
        self._dst_contents: Optional[str] = None

    @classmethod
    def from_path(cls, path: Path, *, must_exist: bool = True) -> FileInfo:
        try:
            with path.open("r", encoding="utf-8", newline="") as fp:
                return cls(path, fp.read())
        except FileNotFoundError:
            if must_exist:
                raise
            return cls(path, "")

    @property
    def contents(self) -> str:
        if self._dst_contents is None:
            return self.src_contents
        return self._dst_contents

    @property
    def dst_contents(self) -> Optional[str]:
        return self._dst_contents

    @dst_contents.setter
    def dst_contents(self, value: str) -> None:
        self._dst_contents = value

    @property
    def changed(self) -> bool:
        return (
            self._dst_contents is not None and self.src_contents != self._dst_contents
        )

    def save(self) -> None:
        if self._dst_contents is None:
            raise RuntimeError("The file wasn't modified.")

        # make sure that the parent folder exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with self.path.open("w", encoding="utf-8", newline="\n") as fp:
            fp.write(self._dst_contents)

    def diff(self) -> str:
        relative_path = self.path.relative_to(ROOT_PATH)
        a_lines = [f"{line}\n" for line in self.src_contents.splitlines()]
        b_lines = [f"{line}\n" for line in self.contents.splitlines()]
        return "".join(
            difflib.unified_diff(
                a_lines,
                b_lines,
                str("a" / relative_path),
                str("b" / relative_path),
            )
        )


class Results:
    def __init__(self, options: Options) -> None:
        self._files: Dict[Path, FileInfo] = {}
        self._options = options

    @property
    def files_changed(self) -> bool:
        return any(file_info.changed for file_info in self._files.values())

    def get_file(self, path: Path) -> str:
        if (file_info := self._files.get(path)) is None:
            self._files[path] = file_info = FileInfo.from_path(path)

        return file_info.contents

    def update_file(self, path: Path, dst_contents: str) -> None:
        if (file_info := self._files.get(path)) is None:
            self._files[path] = file_info = FileInfo.from_path(path, must_exist=False)

        if dst_contents and not dst_contents.endswith("\n"):
            dst_contents += "\n"
        file_info.dst_contents = dst_contents

    def iter_changed_files(self) -> Generator[FileInfo, None, None]:
        for file_info in self._files.values():
            if file_info.changed:
                yield file_info

    def finish_and_print_results(self) -> None:
        save_files = self._options.write_back is WriteBack.YES
        diff = self._options.write_back is WriteBack.DIFF
        text = "updated" if save_files else "would update"
        for file_info in self.iter_changed_files():
            if save_files:
                file_info.save()
            elif diff:
                print(file_info.diff())

            print(f"{text} {file_info.path.relative_to(ROOT_PATH)}")
