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

from typing import TYPE_CHECKING

from ..utils import iter_files_to_format

if TYPE_CHECKING:
    from ..context import InfoGenMainCommand

__all__ = ("LICENSE_HEADER", "update_license_headers")

LICENSE_HEADER = """
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
""".strip()


def update_license_headers(ctx: InfoGenMainCommand) -> bool:
    success = True
    for path in iter_files_to_format():
        source = ctx.results.get_file(path)
        if not source.startswith(LICENSE_HEADER):
            ctx.results.update_file(path, f"{LICENSE_HEADER}\n\n{source}")
            success = False

    return success
