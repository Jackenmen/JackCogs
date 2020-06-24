import rlapi


def username_from_player(player: rlapi.Player) -> str:
    """
    Temporary workaround for payloads that have integers in `user_id` key.

    This uses `Player.player_id`, if `Player.user_id` is not a string.
    """
    return player.user_name if isinstance(player.user_name, str) else player.player_id
