"""Script to automatically download d.py typings PR and extract *.pyi files from it.

Script also saves short hash of the repo at the time of downloading to VENDOR_SHORT_HASH file.

---

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

import re
import shutil
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import requests

ROOT_PATH = Path(__file__).absolute().parent.parent


resp = requests.get(
    "https://codeload.github.com/Rapptz/discord.py/legacy.zip/pull/1497/head"
)
fp = BytesIO(resp.content)
zip_file = ZipFile(fp)

namelist = zip_file.namelist()
top_folder_name = next(name for name in namelist if len(PurePosixPath(name).parts) == 1)

pattern = re.compile(rf"{re.escape(top_folder_name)}discord/.+\.pyi")
to_extract = [name for name in namelist if pattern.fullmatch(name)]
to_extract.append(f"{top_folder_name}LICENSE")

dst = ROOT_PATH / ".stubs" / "discord"

with TemporaryDirectory() as tmpdir:
    zip_file.extractall(tmpdir, members=to_extract)
    extracted_folder = Path(tmpdir) / top_folder_name
    to_copy = extracted_folder / "discord"
    shutil.copytree(to_copy, dst, dirs_exist_ok=True)
    shutil.copy(extracted_folder / "LICENSE", dst / "LICENSE.txt")

_, short_hash = top_folder_name[:-1].rsplit("-", maxsplit=1)
with open(dst / "VENDOR_SHORT_HASH", "w") as f:
    f.write(short_hash)
