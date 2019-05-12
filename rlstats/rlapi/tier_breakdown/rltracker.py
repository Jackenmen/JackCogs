import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from .. import errors
from ..player import RANKS
if TYPE_CHECKING:
    from ..client import Client

log = logging.getLogger(__name__)

__all__ = ('get_tier_breakdown',)

TIER_MAX = len(RANKS)


async def get_tier_breakdown(client: 'Client'):
    # {10:{},11:{},12:{},13:{}}
    tier_breakdown = defaultdict(lambda: defaultdict(dict))

    for tier_id in range(1, TIER_MAX):
        try:
            tier = await _get_division_stats(client, tier_id)
        except errors.HTTPException:
            log.error('Downloading tier breakdown did not succeed.')
            raise

        for breakdown in tier:
            playlist_id = breakdown['playlist_id']
            division = breakdown['division']
            begin = float(breakdown['from'])
            end = float(breakdown['to'])
            tier_breakdown[playlist_id][tier_id][division] = [begin, end]

    return tier_breakdown


async def _get_division_stats(client: 'Client', tier_id):
    url = (
        f'http://rltracker.pro/tier_breakdown/get_division_stats?tier_id={tier_id}'
    )
    return await client._request(url)
