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
This an incomplete stub of traitlets library for use of cogs in this repo.
Nobody have made a full stub for this library so only stuff used by this repo is typed.
"""

from typing import Any, List, Optional, Type, TypeVar

from ..traitlets import HasTraits

_SingletonType = TypeVar("_SingletonType", bound="SingletonConfigurable")

class Configurable(HasTraits): ...
class LoggingConfigurable(Configurable): ...

class SingletonConfigurable(LoggingConfigurable):
    @classmethod
    def clear_instance(cls) -> None: ...
    @classmethod
    def initialized(cls) -> bool: ...
    @classmethod
    def instance(
        cls: Type[_SingletonType], *args: Any, **kwargs: Any
    ) -> _SingletonType: ...
    def initialize(self, argv: Optional[List[str]] = None) -> None: ...
