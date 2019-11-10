__all__ = ("RLStatsException", "PlayerDataNotFound", "NoChoiceError")


class RLStatsException(Exception):
    """Base exception class for RLStats."""


class PlayerDataNotFound(RLStatsException):
    """Couldn't find player data for Discord user."""


class NoChoiceError(RLStatsException):
    """User didn't choose profile which he wants to check."""
