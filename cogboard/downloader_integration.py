from typing import Optional

from redbot.cogs.downloader import Downloader  # DEP-WARN
from redbot.cogs.downloader.repo_manager import Repo  # DEP-WARN
from yarl import URL


def _standardize_url(url: str) -> str:
    url_obj = URL(url)
    # remove trailing slash
    if url_obj.parts[-1] == "":
        return str(url_obj.parent)
    return str(url_obj)


def get_repo_by_url(downloader: Downloader, url: str) -> Optional[Repo]:
    url = _standardize_url(url)
    for repo in downloader._repo_manager.repos:
        if url == _standardize_url(repo.clean_url):
            return repo
    return None
