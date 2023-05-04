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

import warnings

__all__ = ("ignore_ipy_depr_warnings",)


def ignore_ipy_depr_warnings() -> None:
    # silence the deprecation warning from IPython itself
    # https://github.com/ipython/ipykernel/issues/540
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        message="`run_cell_async` will not call `transform_cell` automatically",
    )
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        message="`should_run_async` will not call `transform_cell` automatically",
    )
    # usage of imp library by ipykernel
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, module="ipykernel", lineno=14
    )
