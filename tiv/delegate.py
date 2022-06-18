# Copyright 2018-present Jakub Kuczys (https://github.com/jack1142)
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

import functools
from typing import Any

import discord


def delegate(cls: type, attr_name: str) -> Any:
    meth_or_property = getattr(cls, attr_name)

    @functools.wraps(getattr(meth_or_property, "fget", meth_or_property))
    def func(self: discord.VoiceChannel) -> Any:
        return getattr(cls, attr_name).__get__(self, type(self))

    func.__name__ = attr_name

    return property(func)
