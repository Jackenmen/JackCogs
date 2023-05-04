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

import collections.abc
import re
import typing

from redbot import VersionInfo
from strictyaml import Regex
from strictyaml.exceptions import YAMLSerializationError, YAMLValidationError
from strictyaml.utils import is_string
from strictyaml.yamllocation import YAMLChunk

__all__ = ("PythonVersion", "RedVersion")

if typing.TYPE_CHECKING:
    # TODO: stub strictyaml
    # this is awful workaround (along with the ignore missing imports in mypy.ini)
    ScalarValidator = object
else:
    from strictyaml import ScalarValidator


class PythonVersion(ScalarValidator):
    REGEX = re.compile(r"(\d+)\.(\d+)\.(\d+)")

    def __init__(self) -> None:
        self._matching_message = "when expecting Python version (MAJOR.MINOR.MICRO)"

    def validate_scalar(self, chunk: YAMLChunk) -> typing.List[int]:
        match = self.REGEX.fullmatch(chunk.contents)
        if match is None:
            raise YAMLValidationError(
                self._matching_message, "found non-matching string", chunk
            )
        return [int(group) for group in match.group(1, 2, 3)]

    def to_yaml(self, data: typing.Any) -> str:
        if isinstance(data, collections.abc.Sequence):
            if len(data) != 3:
                raise YAMLSerializationError(
                    f"expected a sequence of 3 elements, got {len(data)} elements"
                )
            for item in data:
                if not isinstance(item, int):
                    raise YAMLSerializationError(
                        f"expected int, got '{item}' of type '{type(item).__name__}'"
                    )
                if item < 0:
                    raise YAMLSerializationError(
                        f"expected non-negative int, got {item}"
                    )
            return ".".join(str(segment) for segment in data)
        if is_string(data):
            # we just validated that it's a string
            version_string = typing.cast(str, data)
            if self.REGEX.fullmatch(version_string) is None:
                raise YAMLSerializationError(
                    "expected Python version (MAJOR.MINOR.MICRO),"
                    f" got '{version_string}'"
                )
            return version_string
        raise YAMLSerializationError(
            "expected string or sequence,"
            f" got '{data}' of type '{type(data).__name__}'"
        )


def RedVersion() -> Regex:
    return Regex(VersionInfo._VERSION_STR_PATTERN.pattern)
