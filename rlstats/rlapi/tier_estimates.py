import asyncio
import logging
from collections import defaultdict
from math import ceil
from typing import Optional, TYPE_CHECKING

import aiohttp

from . import errors
from .utils import json_or_text
if TYPE_CHECKING:
    from .player import Playlist

log = logging.getLogger(__name__)

__all__ = ('TierEstimates',)


class TierEstimates:
    __slots__ = (
        'playlist',
        'tier',
        'division',
        'div_down',
        'div_up',
        'tier_down',
        'tier_up'
    )

    def __init__(self, playlist: 'Playlist'):
        self.playlist = playlist
        if playlist.tier == 0:
            self._estimate_current_tier()
        else:
            self.tier = playlist.tier
            self.division = playlist.division
        self._estimate_div_down()
        self._estimate_div_up()
        self._estimate_tier_down()
        self._estimate_tier_up()

    def _estimate_div_down(self):
        playlist = self.playlist
        if self.tier == 1 and self.division == 0 or self.tier == 0:
            self.div_down = None
            return
        try:
            divisions = playlist.breakdown[self.tier]
            self.div_down = int(
                ceil(
                    divisions[self.division][0] - playlist.skill
                )
            )
        except KeyError as e:
            self.div_down = None
            log.debug(str(e))
            return
        if self.div_down > 0:
            self.div_down = -1

    def _estimate_div_up(self):
        playlist = self.playlist
        if self.tier == self.playlist.tier_max or self.tier == 0:
            self.div_up = None
            return
        try:
            divisions = playlist.breakdown[self.tier]
            if self.tier == self.division == 0:
                value = divisions[1][0]
            else:
                value = divisions[self.division][1]
            self.div_up = int(
                ceil(
                    value - playlist.skill
                )
            )
        except KeyError as e:
            self.div_up = None
            log.debug(str(e))
            return
        if self.div_up < 0:
            self.div_up = 1

    def _estimate_tier_down(self):
        playlist = self.playlist
        if self.tier in {0, 1}:
            self.tier_down = None
            return
        try:
            divisions = playlist.breakdown[self.tier]
            self.tier_down = int(
                ceil(
                    divisions[0][0] - playlist.skill
                )
            )
        except KeyError as e:
            self.tier_down = None
            log.debug(str(e))
            return
        if self.tier_down > 0:
            self.tier_down = -1

    def _estimate_tier_up(self):
        playlist = self.playlist
        if self.tier in {0, self.playlist.tier_max}:
            self.tier_up = None
            return
        try:
            divisions = playlist.breakdown[self.tier]
            self.tier_up = int(
                ceil(
                    divisions[3][1] - playlist.skill
                )
            )
        except KeyError as e:
            self.tier_up = None
            log.debug(str(e))
            return
        if self.tier_up < 0:
            self.tier_up = 1

    def _estimate_current_tier(self):
        playlist = self.playlist
        if not playlist.breakdown:
            self.tier = playlist.tier
            self.division = playlist.division
            return
        if playlist.skill < playlist.breakdown[1][1][0]:
            self.tier = 1
            self.division = 0
            return
        if playlist.skill > playlist.breakdown[playlist.tier_max][0][1]:
            self.tier = playlist.tier_max
            self.division = 0
            return
        for tier, divisions in playlist.breakdown.items():
            for division, data in divisions.items():
                if data[0] <= playlist.skill <= data[1]:
                    self.tier = tier
                    self.division = division
                    return
        self.tier = playlist.tier
        self.division = playlist.division

    @staticmethod
    async def get_tier_breakdown(*, session: Optional[aiohttp.ClientSession] = None):
        # {10:{},11:{},12:{},13:{}}
        tier_breakdown = defaultdict(lambda: defaultdict(dict))

        if session is None:
            session = aiohttp.ClientSession()
        for tier_id in range(1, 20):
            try:
                tier = await TierEstimates._get_division_stats(tier_id, session=session)
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

    @staticmethod
    async def _get_division_stats(tier_id, *, session: aiohttp.ClientSession):
        url = (
            f'http://rltracker.pro/tier_breakdown/get_division_stats?tier_id={tier_id}'
        )
        for tries in range(5):
            async with session.get(url) as resp:
                data = await json_or_text(resp)
                if 300 > resp.status >= 200:
                    return data

                # received 500 or 502 error, RLTracker.pro has some troubles, retrying
                if resp.status in {500, 502}:
                    await asyncio.sleep(1 + tries * 2, loop=session.loop)
                    continue
                # generic error
                raise errors.HTTPException(resp, data)
        # still failed after 5 tries
        raise errors.HTTPException(resp, data)
