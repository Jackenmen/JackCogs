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
Script to automatically generate info.json files
and generate class docstrings from single info.yaml file for whole repo.

DISCLAIMER: While this script works, it uses some hacks and I don't recommend using it
if you don't understand how it does some stuff and why it does it like this.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parent))

import _infogen  # noqa: E402

if __name__ == "__main__":
    success = _infogen.main()
    sys.exit(int(not success))
