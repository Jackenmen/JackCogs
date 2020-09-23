# Copyright 2018-2020 Jakub Kuczys (https://github.com/jack1142)
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
These type hints are terrible, but that's because Red's type hints are terrible
and these have to be compatible... Yes, I know how that sounds.
"""

from typing import (
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Generator,
    Protocol,
    TypeVar,
    Union,
    overload,
)

from redbot.core.commands import Context

_CT = TypeVar("_CT", bound=Context)
_T = TypeVar("_T")
CoroLike = Callable[..., Union[Awaitable[_T], Generator[Any, None, _T]]]


class CheckDecorator(Protocol):
    predicate: Coroutine[Any, Any, bool]

    @overload
    def __call__(self, func: _CT) -> _CT:
        ...

    @overload
    def __call__(self, func: CoroLike[Any]) -> CoroLike[Any]:
        ...
