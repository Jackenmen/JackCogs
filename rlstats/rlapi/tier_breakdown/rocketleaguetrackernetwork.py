import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from lxml import etree

from .. import errors
from ..enums import PlaylistKey
from ..player import RANKS, DIVISIONS
from ..utils import stringify
if TYPE_CHECKING:
    from ..client import Client

log = logging.getLogger(__name__)

__all__ = ('get_tier_breakdown',)


async def get_tier_breakdown(client: 'Client'):
    tier_breakdown = defaultdict(lambda: defaultdict(dict))

    for playlist_key in PlaylistKey:
        playlist_id = playlist_key.value
        try:
            text = await _get_playlist_breakdown(client, playlist_id)
        except errors.HTTPException:
            log.error('Downloading tier breakdown did not succeed.')
            raise
        tiers = etree.HTML(text).findall(
            './body/div[@class="container content-container"]'
            '/div/div/div[@class="row"]/div[@class="col-md-4"]'
        )

        for tier_div in tiers:
            tier_name = stringify(tier_div.find('./h3'))
            try:
                tier_id = RANKS.index(tier_name)
            except ValueError:
                continue

            for division_div in tier_div.iterfind(
                './div/div[@class="division-label"]/..'
            ):
                division_name = stringify(
                    division_div.find('./div[@class="division-label"]')
                )
                if not division_name.startswith('Division '):
                    continue
                try:
                    division_id = DIVISIONS.index(division_name[9:])
                except ValueError:
                    continue

                division_breakdown = division_div.iterfind(
                    './div[@class="division"]/div'
                )
                begin = int(next(division_breakdown).text)
                next(division_breakdown)
                end = int(next(division_breakdown).text)
                tier_breakdown[playlist_id][tier_id][division_id] = [begin, end]
        tier_breakdown[playlist_id].pop(0, None)

    return tier_breakdown


async def _get_playlist_breakdown(client, playlist_id):
    url = (
        f'https://rocketleague.tracker.network/distribution/{playlist_id}'
    )
    return await client._request(url)
