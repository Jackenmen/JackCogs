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
This an incomplete stub of ipykernel library for use of cogs in this repo.
Nobody have made a full stub for this library so only stuff used by this repo is typed.
"""

from typing import List

from IPython.core.interactiveshell import InteractiveShell

class ZMQInteractiveShell(InteractiveShell):
    _last_traceback: List[str]
