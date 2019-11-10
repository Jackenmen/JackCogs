import aiohttp


class CogBoardException(Exception):
    """Base exception class for CogBoard cog exception."""


class CacheRefreshFailed(CogBoardException):
    """Exception that's thrown when cache refresh fails."""


class HTTPException(CogBoardException):
    """Exception that's thrown when an HTTP request operation fails.

    Attributes
    ----------
    response: aiohttp.ClientResponse
        The response of the failed HTTP request.
    status: int
        The status code of the HTTP request.
    """

    def __init__(self, response: aiohttp.ClientResponse):
        self.response = response
        self.status = response.status
        super().__init__(f"{self.response.reason} (status code: {self.status})")
