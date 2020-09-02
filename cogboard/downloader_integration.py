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

from typing import Optional

from redbot.cogs.downloader.downloader import Downloader  # DEP-WARN
from redbot.cogs.downloader.repo_manager import Repo  # DEP-WARN
from yarl import URL


def _standardize_url(url: str) -> str:
    url_obj = URL(url)
    # remove trailing slash
    if url_obj.parts[-1] == "":
        url_obj = url_obj
    new_url = str(url_obj)
    if new_url.endswith(".git"):
        return new_url[:-4]
    return new_url


def get_repo_by_url(downloader: Downloader, url: str) -> Optional[Repo]:
    url = _standardize_url(url)
    for repo in downloader._repo_manager.repos:
        if url == _standardize_url(repo.clean_url):
            return repo
    return None
