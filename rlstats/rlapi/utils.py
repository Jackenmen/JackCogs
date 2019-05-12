import json

import aiohttp
from lxml import etree

__all__ = ('json_or_text',)


_stringify = etree.XPath("string()")


def stringify(element):
    return _stringify(element).strip()


async def json_or_text(resp):
    text = await resp.text(encoding='utf-8')
    if 'application/json' in resp.headers[aiohttp.hdrs.CONTENT_TYPE]:
        return json.loads(text)
    return text
