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

from typing import Dict, Optional, Tuple

from redbot import VersionInfo

__all__ = ("MAX_PYTHON_VERSION", "MAX_RED_VERSIONS")

MAX_RED_VERSIONS: Dict[Tuple[int, int], Optional[VersionInfo]] = {
    (3, 8): None,
}
MAX_PYTHON_VERSION = next(reversed(MAX_RED_VERSIONS.keys()))
