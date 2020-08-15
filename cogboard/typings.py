from typing import TypedDict


class RepoItem(TypedDict):
    author: str
    repo_url: str
    branch: str
    repo_name: str


class CogItem(TypedDict):
    repo_name: str
    name: str
    description: str
