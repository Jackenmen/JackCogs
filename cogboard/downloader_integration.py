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
