"""
Copyright 2018-2020 Jakub Kuczys (https://github.com/jack1142)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import string
from types import SimpleNamespace
from typing import Dict, List, Set

import parso

__all__ = ("scan_recursively",)


def scan_recursively(
    children: List[parso.tree.NodeOrLeaf], name: str, containers: Set[str]
):
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
    def __init__(self, key):
        self.key = key

    def __format__(self, spec):
        result = self.key
        if spec:
            result += ":" + spec
        return "{" + result + "}"

    def __getitem__(self, index):
        self.key = f"{self.key}[{index}]"
        return self

    def __getattr__(self, attr):
        self.key = f"{self.key}.{attr}"
        return self


class _FormatDict(dict):
    def __missing__(self, key):
        return _FormatPlaceholder(key)
