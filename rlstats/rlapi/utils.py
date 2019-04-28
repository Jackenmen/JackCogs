import json

import aiohttp

__all__ = ('json_or_text',)


async def json_or_text(resp):
    text = await resp.text(encoding='utf-8')
    if 'application/json' in resp.headers[aiohttp.hdrs.CONTENT_TYPE]:
        return json.loads(text)
    return text
