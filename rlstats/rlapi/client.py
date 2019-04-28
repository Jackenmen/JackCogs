import asyncio
import logging
import re
from typing import Tuple, Set, List, Dict, Optional

import defusedxml.ElementTree as ET
import aiohttp

from . import errors
from .enums import Platform, PlatformPatterns
from .player import Player
from .tier_estimates import TierEstimates
from .utils import json_or_text

log = logging.getLogger(__name__)

__all__ = ('Client',)


class Client:
    RLAPI_BASE = 'https://api.rocketleague.com/api/v1'
    STEAM_BASE = 'https://steamcommunity.com'

    def __init__(
        self,
        token: str,
        *,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        tier_breakdown: Optional[Dict[int, Dict[int, Dict[int, List[float]]]]] = None
    ):
        self.loop = asyncio.get_event_loop() if loop is None else loop
        self._session = aiohttp.ClientSession(loop=self.loop)
        self._token = token
        self.tier_breakdown = tier_breakdown
        self.setup = self.loop.create_task(self._setup())

    async def _setup(self):
        if not self.tier_breakdown:
            await self.update_tier_breakdown()

    def destroy(self):
        self._session.detach()
        self.setup.cancel()

    __del__ = destroy

    async def update_tier_breakdown(self):
        self.tier_breakdown = await TierEstimates.get_tier_breakdown(
            session=self._session
        )

    def update_token(self, token: str):
        self._token = token

    async def _rlapi_request(self, endpoint):
        url = self.RLAPI_BASE + endpoint
        headers = {
            'Authorization': f'Token {self._token}'
        }
        for tries in range(5):
            async with self._session.get(url, headers=headers) as resp:
                data = await json_or_text(resp)
                if 300 > resp.status >= 200:
                    return data

                # received 500 or 502 error, RL API has some troubles, retrying
                if resp.status in {500, 502}:
                    await asyncio.sleep(1 + tries * 2, loop=self.loop)
                    continue
                # token is invalid
                if resp.status == 401:
                    raise errors.Unauthorized(resp, data['detail'])
                # generic error
                raise errors.HTTPException(resp, data)
        # still failed after 5 tries
        raise errors.HTTPException(resp, data)

    async def _get_stats(self, player_id: str, platform: Platform) -> Player:
        """
        Get player skills for player ID in selected platform.

        Parameters
        ----------
        platform: Platform
            Platform to search.
        player_id: `str`
            ID of player to find.

        Returns
        -------
        Player
            Requested player skills.

        Raises
        ------
        HTTPException
            HTTP request to Rocket League API failed.
        PlayerNotFound
            The player could not be found.

        """
        await self.setup
        endpoint = f'/{platform.name}/playerskills/{player_id}/'
        try:
            player = await self._rlapi_request(endpoint)
        except errors.HTTPException as e:
            if e.status == 400 and 'not found' in e.message:
                raise errors.PlayerNotFound(
                    "Player with provided ID could not be "
                    f"found on platform {platform.name}"
                )
            raise

        player[0]['platform'] = platform
        return Player(**player[0], tier_breakdown=self.tier_breakdown)

    async def get_player(
        self, player_id: str, platform: Optional[Platform] = None
    ) -> Tuple[Player]:
        """
        Get player skills for player ID by searching in all platforms.

        Parameters
        ----------
        player_id: `str`
            ID of player to find.

        Returns
        -------
        `tuple` of `Player`
            Requested player skills.

        Raises
        ------
        HTTPException
            HTTP request to Rocket League or Steam API failed.
        PlayerNotFound
            The player could not be found on any platform.

        """
        if platform is not None:
            return (await self._get_stats(player_id, platform),)

        players = []
        for platform in Platform:
            try:
                players += await self._find_profile(platform, player_id)
            except errors.IllegalUsername as e:
                log.debug(str(e))
        if not players:
            raise errors.PlayerNotFound(
                "Player with provided ID could not be found on any platform."
            )

        return tuple(players)

    async def _find_profile(self, platform: Platform, player_id: str) -> Set[Player]:
        pattern = PlatformPatterns[platform.name].value
        match = pattern.fullmatch(player_id)
        if not match:
            raise errors.IllegalUsername(
                f"Provided username doesn't match provided pattern: {pattern}"
            )

        players = set()
        if platform == Platform.steam:
            ids = await self._find_steam_ids(match)
        else:
            ids = [player_id]

        for player_id_to_find in ids:
            try:
                player = await self._get_stats(player_id_to_find, platform)
                players.add(player)
            except errors.PlayerNotFound as e:
                log.debug(str(e))
        return players

    async def _find_steam_ids(self, match: re.Match) -> List[str]:
        player_id = match.group(2)
        search_type = match.group(1)
        if search_type is None:
            search_types = ['profiles', 'id']
        else:
            search_types = [search_type]
        ids = []
        for search_type in search_types:
            url = self.STEAM_BASE + f'/{search_type}/{player_id}/?xml=1'
            async with self._session.get(url) as resp:
                if resp.status >= 400:
                    raise errors.HTTPException(resp, await resp.text())
                steam_profile = ET.fromstring(await resp.text())

            error = steam_profile.find('error')
            if error is None:
                ids.append(steam_profile.find('steamID64').text)
            elif error.text != 'The specified profile could not be found.':
                log.debug(
                    "Steam threw error while searching profile using '%s' method: %s",
                    search_type, error.text
                )

        return ids
