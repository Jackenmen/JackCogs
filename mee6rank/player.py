# Copyright 2018-present Jakub Kuczys (https://github.com/Jackenmen)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import math
from functools import cached_property
from io import BytesIO
from typing import Any, Dict, List, Optional

import discord


class Player:
    def __init__(
        self,
        player_data: Dict[str, Any],
        member: discord.Member,
        role_rewards: List[Dict[str, Any]],
    ) -> None:
        self._player_data = player_data
        self.member = member
        self.guild = member.guild
        self.role_rewards = self._generate_role_rewards_list(role_rewards)

        self.level_xp: int
        self.level_total_xp: int
        self.total_xp: int
        self.level_xp, self.level_total_xp, self.total_xp = player_data["detailed_xp"]

        self.level: int = player_data["level"]
        self.rank: int = player_data["rank"]
        self.message_count: int = player_data["message_count"]

    def _generate_role_rewards_list(
        self, role_rewards: List[Dict[str, Any]]
    ) -> List[RoleReward]:
        ret = []
        for data in role_rewards:
            role = self.guild.get_role(int(data["role"]["id"]))
            if role is None:
                continue
            ret.append(RoleReward(data["rank"], role))
        ret.sort()
        return ret

    @cached_property
    def next_role_reward(self) -> Optional[RoleReward]:
        for role_reward in self.role_rewards:
            if role_reward.rank > self.level:
                return role_reward
        return None

    @cached_property
    def xp_until_next_level(self) -> int:
        return self.level_total_xp - self.level_xp

    def xp_until_level(self, level: int) -> int:
        if level <= self.level:
            raise ValueError("Player has already reached the passed `level`")
        # formula taken from https://github.com/PsKramer/mee6calc/blob/master/calc.js
        needed_total_xp = math.ceil(
            5 / 6 * level * (2 * level * level + 27 * level + 91)
        )
        return needed_total_xp - self.total_xp


class PlayerWithAvatar(Player):
    def __init__(
        self,
        player_data: Dict[str, Any],
        member: discord.Member,
        role_rewards: List[Dict[str, Any]],
        avatar: BytesIO,
    ) -> None:
        super().__init__(player_data, member, role_rewards)
        self.avatar = avatar


class RoleReward:
    def __init__(self, rank: int, role: discord.Role) -> None:
        self.rank = rank
        self.role = role

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, RoleReward):
            return self.rank < other.rank
        return NotImplemented

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, RoleReward):
            return self.rank > other.rank
        return NotImplemented

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, RoleReward):
            return self.rank == other.rank
        return NotImplemented

    def __ne__(self, other: Any) -> bool:
        if isinstance(other, RoleReward):
            return self.rank != other.rank
        return NotImplemented
