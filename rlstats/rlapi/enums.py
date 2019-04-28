import re
from enum import Enum

__all__ = ('PlaylistKey', 'Platform', 'PlatformPatterns')


class PlaylistKey(Enum):
    SOLO_DUEL = 10
    DOUBLES = 11
    SOLO_STANDARD = 12
    STANDARD = 13
    HOOPS = 27
    RUMBLE = 28
    DROPSHOT = 29
    SNOW_DAY = 30

    def __str__(self):
        return str(self.value)

    @property
    def friendly_name(self):
        # pylint: disable=no-member
        return self.name.replace('_', ' ').title()


class Platform(Enum):
    steam = 'Steam'
    ps4 = 'Playstation 4'
    xboxone = 'Xbox One'

    def __str__(self):
        return self.value


class PlatformPatterns(Enum):
    steam = re.compile(r"""
        (?:
            (?:https?:\/\/(?:www\.)?)?steamcommunity\.com\/
            (id|profiles)\/         # group 1 - None if input is only a username/id
        )?
        ([a-zA-Z0-9_-]{2,32})\/?    # group 2
    """, re.VERBOSE)
    ps4 = re.compile('[a-zA-Z][a-zA-Z0-9_-]{2,15}')
    xboxone = re.compile('[a-zA-Z](?=.{0,15}$)([a-zA-Z0-9-_]+ ?)+')
