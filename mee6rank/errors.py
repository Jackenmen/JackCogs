from typing import Any, Dict, Union

import aiohttp


class Mee6RankException(Exception):
    """Base exception class for Mee6Rank cog."""


class HTTPException(Mee6RankException):
    """Exception that's thrown when an HTTP request operation fails.

    Attributes
    ----------
    response: aiohttp.ClientResponse
        The response of the failed HTTP request.
    status: int
        The status code of the HTTP request.
    error_message: str, optional
        Details about error.
    """

    def __init__(
        self, response: aiohttp.ClientResponse, data: Union[Dict[str, Any], str]
    ) -> None:
        self.response = response
        self.status = response.status
        self.error_message = None
        if isinstance(data, dict):
            try:
                self.error_message = data["error"]["message"]
            except (KeyError, TypeError):
                pass
        super().__init__(
            f"{self.response.reason} (status code: {self.status})"
            + (f": {self.error_message}" if self.error_message else "")
        )


class GuildNotFound(HTTPException):
    """Exception that's thrown when there's no Mee6 leaderboard for given guild."""
