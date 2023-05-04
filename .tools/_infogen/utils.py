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

import functools
import re
import string
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Generator, Iterable, List, Literal, Pattern, Set, overload

import parso
import tomli
from parso.tree import NodeOrLeaf
from pathspec import PathSpec

from . import ROOT_PATH

__all__ = (
    "get_gitignore",
    "iter_files",
    "iter_files_to_format",
    "safe_format_alt",
    "scan_recursively",
)


# these overloads are incomplete and only overload string literals used in this package
@overload
def scan_recursively(
    children: List[NodeOrLeaf], name: Literal["async_funcdef"], containers: Set[str]
) -> Generator[parso.python.tree.Function, None, None]:
    ...


@overload
def scan_recursively(
    children: List[NodeOrLeaf], name: Literal["name"], containers: Set[str]
) -> Generator[parso.python.tree.Name, None, None]:
    ...


@overload
def scan_recursively(
    children: List[NodeOrLeaf], name: str, containers: Set[str]
) -> Generator[NodeOrLeaf, None, None]:
    ...


def scan_recursively(
    children: List[NodeOrLeaf], name: str, containers: Set[str]
) -> Generator[NodeOrLeaf, None, None]:
    for element in children:
        if element.type == name:
            yield element
        if element.type in containers:
            # `containers` contains only types with children
            assert isinstance(element, parso.tree.BaseNode), "mypy"
            for e in scan_recursively(element.children, name, containers):
                yield e


# `FormatPlaceholder`, `FormatDict` and `safe_format_alt` taken from
# https://stackoverflow.com/posts/comments/100958805


def safe_format_alt(text: str, source: Dict[str, SimpleNamespace]) -> str:
    formatter = string.Formatter()
    return formatter.vformat(text, (), _FormatDict(source))


class _FormatPlaceholder:
    def __init__(self, key: str) -> None:
        self.key = key

    def __format__(self, format_spec: str) -> str:
        result = self.key
        if format_spec:
            result += ":" + format_spec
        return "{" + result + "}"

    def __getitem__(self, index: Any) -> _FormatPlaceholder:
        self.key = f"{self.key}[{index}]"
        return self

    def __getattr__(self, attr: str) -> _FormatPlaceholder:
        self.key = f"{self.key}.{attr}"
        return self


class _FormatDict(Dict[str, Any]):
    def __missing__(self, key: str) -> _FormatPlaceholder:
        return _FormatPlaceholder(key)


def _get_black_config() -> Dict[str, Any]:
    """
    Get Black's config.

    This function has been copied from Black (https://github.com/psf/black).
    """
    with open(ROOT_PATH / "pyproject.toml", "rb") as fp:
        pyproject_toml = tomli.load(fp)
    config = pyproject_toml.get("tool", {}).get("black", {})
    return {k.replace("--", "").replace("-", "_"): v for k, v in config.items()}


def _re_compile_maybe_verbose(regex: str) -> Pattern[str]:
    """Compile a regular expression string in `regex`.
    If it contains newlines, use verbose mode.
    """
    if "\n" in regex:
        regex = "(?x)" + regex
    compiled: Pattern[str] = re.compile(regex)
    return compiled


@functools.lru_cache()
def get_gitignore() -> PathSpec:
    """
    Return a PathSpec matching gitignore content if present.

    This function has been copied from Black (https://github.com/psf/black).
    """
    gitignore = ROOT_PATH / ".gitignore"
    lines: List[str] = []
    if gitignore.is_file():
        with gitignore.open() as gf:
            lines = gf.readlines()
    return PathSpec.from_lines("gitwildmatch", lines)


def iter_files(
    paths: Iterable[Path],
    include: Pattern[str],
    exclude: Pattern[str],
    gitignore: PathSpec,
) -> Generator[Path, None, None]:
    """
    Iterate through all files matching given parameters.

    Highly influenced by Black (https://github.com/psf/black).
    """
    for child in paths:
        normalized = child.relative_to(ROOT_PATH).as_posix()
        if gitignore.match_file(normalized):
            continue

        normalized = f"/{normalized}"
        if child.is_dir():
            normalized += "/"

        exclude_match = exclude.search(normalized)
        if exclude_match is not None and exclude_match.group(0):
            continue

        if child.is_dir():
            yield from iter_files(child.iterdir(), include, exclude, gitignore)
        elif child.is_file():
            if include.search(normalized) is not None:
                yield child


def iter_files_to_format() -> Generator[Path, None, None]:
    """Iterate through all files that should be formatted by Black."""
    black_config = _get_black_config()
    gitignore = get_gitignore()

    include = _re_compile_maybe_verbose(black_config.get("ignore", r"\.pyi?$"))
    exclude = _re_compile_maybe_verbose(black_config["force_exclude"])

    yield from iter_files(ROOT_PATH.iterdir(), include, exclude, gitignore)
