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
