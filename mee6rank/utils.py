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

import json
from typing import Any, Dict, Union

import aiohttp

_BASE = 1000


def natural_size(value: Union[float, int]) -> str:
    if value < _BASE:
        return str(value)
    for power, suffix in enumerate("KMGTPEZY", 2):
        unit = _BASE**power
        if value < unit:
            return f"{_BASE * value / unit:.2f}{suffix}"
    return f"{_BASE * value / unit:.2f}{suffix}"


async def json_or_text(resp: aiohttp.ClientResponse) -> Union[Dict[str, Any], str]:
    """
    Returns json dict, if response's content type is json,
    or raw text otherwise.

    Parameters
    ----------
    resp: `aiohttp.ClientResponse`
        Response object

    Returns
    -------
    `dict` or `str`
        Response data.

    """
    text = await resp.text(encoding="utf-8")
    if "application/json" in resp.headers.get(aiohttp.hdrs.CONTENT_TYPE, ""):
        data = json.loads(text)
        assert isinstance(data, dict), "mypy"
        return data
    return text
