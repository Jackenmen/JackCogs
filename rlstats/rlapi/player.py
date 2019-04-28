import contextlib

from .enums import Platform, PlaylistKey
from .tier_estimates import TierEstimates

RANKS = (
    'Unranked',
    'Bronze I',
    'Bronze II',
    'Bronze III',
    'Silver I',
    'Silver II',
    'Silver III',
    'Gold I',
    'Gold II',
    'Gold III',
    'Platinum I',
    'Platinum II',
    'Platinum III',
    'Diamond I',
    'Diamond II',
    'Diamond III',
    'Champion I',
    'Champion II',
    'Champion III',
    'Grand Champion'
)
DIVISIONS = ('I', 'II', 'III', 'IV')

__all__ = ('Playlist', 'SeasonRewards', 'Player')


class Playlist:
    __slots__ = (
        'key',
        'tier',
        'division',
        'mu',
        'skill',
        'sigma',
        'win_streak',
        'matches_played',
        'tier_max',
        'breakdown',
        'tier_estimates'
    )

    def __init__(self, **kwargs):
        self.key = kwargs.get('key')
        self.tier = kwargs.get('tier', 0)
        self.division = kwargs.get('division', 0)
        self.mu = kwargs.get('mu', 25)
        self.skill = kwargs.get('skill', self.mu*20+100)
        self.sigma = kwargs.get('sigma', 8.333)
        self.win_streak = kwargs.get('win_streak', 0)
        self.matches_played = kwargs.get('matches_played', 0)
        self.tier_max = kwargs.get('tier_max', 19)
        self.breakdown = kwargs.get('breakdown', {})
        self.tier_estimates = TierEstimates(self)

    def __str__(self):
        try:
            if self.tier in [0, self.tier_max]:
                return RANKS[self.tier]
            return '{} Div {}'.format(RANKS[self.tier], DIVISIONS[self.division])
        except IndexError:
            return 'Unknown'


class SeasonRewards:
    __slots__ = ('level', 'wins', 'reward_ready')

    def __init__(self, **kwargs):
        self.level = kwargs.get('level', 0)
        if self.level is None:
            self.level = 0
        self.wins = kwargs.get('wins', 0)
        if self.wins is None:
            self.wins = 0
        highest_tier = kwargs.get('highest_tier', 0)
        if self.level == 0 or self.level * 3 < highest_tier:
            self.reward_ready = True
        else:
            self.reward_ready = False


class Player:
    """Represents Rocket League Player

    Attributes
    ----------
    platform : Platform
        Player's platform. There is a chance that the type will be `int` if
        the platform type is not within the ones recognised by the enumerator.

    """
    __slots__ = (
        'platform',
        'user_name',
        'player_id',
        'playlists',
        'tier_breakdown',
        'highest_tier',
        'season_rewards'
    )

    def __init__(self, **kwargs):
        self.platform = kwargs.get('platform')
        with contextlib.suppress(KeyError):
            self.platform = Platform[self.platform]
        self.user_name = kwargs.get('user_name')
        self.player_id = kwargs.get('user_id', self.user_name)
        self.playlists = {}
        player_skills = kwargs.get('player_skills', [])
        self.tier_breakdown = kwargs.get('tier_breakdown', {})
        self._prepare_playlists(player_skills)
        if self.playlists:
            self.highest_tier = []
            for playlist in self.playlists.values():
                self.highest_tier.append(playlist.tier)
            self.highest_tier = max(self.highest_tier)
        else:
            self.highest_tier = 0
        self.season_rewards = kwargs.get('season_rewards', {})
        self.season_rewards['highest_tier'] = self.highest_tier
        self.season_rewards = SeasonRewards(**self.season_rewards)

    def get_playlist(self, playlist_key):
        return self.playlists.get(playlist_key)

    def add_playlist(self, playlist):
        playlist['key'] = playlist.pop('playlist')
        breakdown = self.tier_breakdown.get(playlist['key'], {})
        with contextlib.suppress(ValueError):
            playlist['key'] = PlaylistKey(playlist['key'])

        self.playlists[playlist['key']] = Playlist(
            **playlist, breakdown=breakdown
        )

    def _prepare_playlists(self, player_skills):
        for playlist in player_skills:
            self.add_playlist(playlist)
