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

from typing import Any, Dict, Literal

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands import GuildContext, NoParseOptional as Optional
from redbot.core.config import Config
from redbot.core.utils.chat_formatting import box
from redbot.core.utils.mod import is_mod_or_superior

from .converters import AssignableRoleConverter as AssignableRole

RequestType = Literal["discord_deleted_user", "owner", "user", "user_strict"]


class ModRoles(commands.Cog):
    """Allow moderators to assign configured roles to users."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=176070082584248320, force_registration=True
        )
        self.config.register_guild(
            assignable_roles=[], allow_bots=False, toprole_check=True
        )

    async def red_get_data_for_user(self, *, user_id: int) -> Dict[str, Any]:
        # this cog does not story any data
        return {}

    async def red_delete_data_for_user(
        self, *, requester: RequestType, user_id: int
    ) -> None:
        # this cog does not story any data
        pass

    async def _assign_checks(
        self, ctx: GuildContext, member: discord.Member, role: discord.Role
    ) -> bool:
        author = ctx.author
        guild = ctx.guild
        if await self.bot.is_owner(author):
            return True
        if author.id == guild.owner_id:
            return True
        settings = await self.config.guild(guild).all()
        if not settings["allow_bots"] and member.bot:
            await ctx.send("Pfft, you can't apply roles to bots.")
            return False
        if role > author.top_role:
            await ctx.send("You can only assign roles that are below your top role!")
            return False
        if author.id == member.id:
            return True
        if settings["toprole_check"] and member.top_role > author.top_role:
            await ctx.send(
                "You can only assign roles to members"
                " whose top role is lower than yours!"
            )
            return False
        if await is_mod_or_superior(self.bot, member):
            await ctx.send("You can't assign roles to member who is mod or higher.")
            return False
        return True

    @commands.guild_only()
    @commands.bot_has_permissions(manage_roles=True)
    @commands.mod_or_permissions(manage_roles=True)
    @commands.command()
    async def assignrole(
        self, ctx: GuildContext, role: AssignableRole, *, member: discord.Member
    ) -> None:
        """
        Assign a role to a member.

        NOTE: The role is case sensitive!
        """
        if member.get_role(role.id) is not None:
            await ctx.send(f'{member.display_name} already has "{role.name}" role.')
            return
        if not await self._assign_checks(ctx, member, role):
            return
        if role >= ctx.guild.me.top_role:
            await ctx.send(
                f"I can't give {role.name} to {member.display_name}"
                " because that role is higher than or equal to my highest role"
                " in the Discord hierarchy."
            )
            return
        try:
            await member.add_roles(role)
        except discord.Forbidden:
            await ctx.send(
                "I attempted to do something that Discord denied me"
                " permissions for. Your command failed to successfully complete."
            )
        else:
            await ctx.send(f"Role {role.name} added to {member.display_name}")

    @commands.guild_only()
    @commands.bot_has_permissions(manage_roles=True)
    @commands.mod_or_permissions(manage_roles=True)
    @commands.command()
    async def unassignrole(
        self, ctx: GuildContext, role: AssignableRole, *, member: discord.Member
    ) -> None:
        """
        Unassign a role from a member.

        NOTE: The role is case sensitive!
        """
        if member.get_role(role.id) is None:
            await ctx.send(f'{member.display_name} doesn\'t have "{role.name}" role.')
            return
        if not await self._assign_checks(ctx, member, role):
            return
        if role >= ctx.guild.me.top_role:
            await ctx.send(
                f"I can't remove {role.name} from {member.display_name}"
                " because that role is higher than or equal to my highest role"
                " in the Discord hierarchy."
            )
            return
        try:
            await member.remove_roles(role)
        except discord.Forbidden:
            await ctx.send(
                "I attempted to do something that Discord denied me"
                " permissions for. Your command failed to successfully complete."
            )
        else:
            await ctx.send(f"Role {role.name} removed from {member.display_name}")

    @commands.guild_only()
    @commands.admin_or_permissions(manage_roles=True)
    @commands.group()
    async def modroles(self, ctx: GuildContext) -> None:
        """Settings for assignable roles."""

    @modroles.command(name="add")
    async def modroles_add(self, ctx: GuildContext, *, role: discord.Role) -> None:
        """Add assignable role."""
        if (
            ctx.guild.owner_id != ctx.author.id
            and role > ctx.author.top_role
            and not await self.bot.is_owner(ctx.author)
        ):
            await ctx.send(
                "You can't add a role that is above your top role as assignable!"
            )
            return
        if role >= ctx.guild.me.top_role:
            await ctx.send(
                "You can't add this role as assignable because it is"
                " higher than or equal to my highest role in the Discord hierarchy."
            )
            return
        conf_group = self.config.guild(ctx.guild).assignable_roles
        assignable_roles = await conf_group()
        if role.id in assignable_roles:
            await ctx.send("This role is already assignable.")
            return
        assignable_roles.append(role.id)
        await conf_group.set(assignable_roles)
        await ctx.send(f"Role {role.name} added to assignable roles.")

    @modroles.command(name="remove")
    async def modroles_remove(self, ctx: GuildContext, *, role: AssignableRole) -> None:
        """Remove assignable role."""
        if (
            ctx.guild.owner_id != ctx.author.id
            and role > ctx.author.top_role
            and not await self.bot.is_owner(ctx.author)
        ):
            await ctx.send("You can't remove a role that is above your top role!")
            return
        async with self.config.guild(ctx.guild).assignable_roles() as assignable_roles:
            assignable_roles.remove(role.id)
        await ctx.send(f"Role {role.name} removed from assignable roles.")

    @modroles.command(name="list")
    async def modroles_list(self, ctx: GuildContext) -> None:
        """List assignable roles."""
        assignable_roles = set(await self.config.guild(ctx.guild).assignable_roles())
        valid_roles = tuple(r for r in ctx.guild.roles if r.id in assignable_roles)
        valid_roles_ids = set(r.id for r in valid_roles)

        if assignable_roles != valid_roles_ids:
            await self.config.guild(ctx.guild).assignable_roles.set(
                list(valid_roles_ids)
            )

        fmt_assignable_roles = "\n".join([f"+ {r.name}" for r in valid_roles])

        await ctx.send(
            box(f"Available assignable roles:\n{fmt_assignable_roles}", "diff")
        )

    @modroles.group(name="targets")
    async def modroles_targets(self, ctx: GuildContext) -> None:
        """Settings about allowed targets."""

    @modroles_targets.command(name="allowbots")
    async def modroles_targets_allowbots(
        self, ctx: GuildContext, enabled: Optional[bool] = None
    ) -> None:
        """
        Allow to assign roles to bots with `[p]assignrole`

        Leave empty to check current settings.
        """
        config_value = self.config.guild(ctx.guild).allow_bots
        if enabled is None:
            if await config_value():
                message = (
                    "Commands for assigning and unassigning roles"
                    " can be used on bots in this server."
                )
            else:
                message = (
                    "Commands for assigning and unassigning roles"
                    " cannot be used on bots in this server."
                )
            await ctx.send(message)
            return

        await config_value.set(enabled)

        if enabled:
            message = (
                "Commands for assigning and unassigning roles"
                " can now be used on bots in this server."
            )
        else:
            message = (
                "Commands for assigning and unassigning roles"
                " can no longer be used on bots in this server."
            )
        await ctx.send(message)

    @modroles_targets.command(name="toprole")
    async def modroles_targets_toprole(
        self, ctx: GuildContext, enabled: Optional[bool] = None
    ) -> None:
        """
        Enable/disable top role check.

        When enabled, this will only allow user to assign roles to users
        with lower top role than theirs.

        Leave empty to check current settings.
        """
        config_value = self.config.guild(ctx.guild).toprole_check
        if enabled is None:
            if await config_value():
                message = (
                    "Commands for assigning and unassigning roles only allow command"
                    " caller to assign roles to users with lower top role than theirs."
                )
            else:
                message = (
                    "Commands for assigning and unassigning roles"
                    " allow command caller to assign roles to any user."
                )
            await ctx.send(message)
            return

        await config_value.set(enabled)

        if enabled:
            message = (
                "Commands for assigning and unassigning roles"
                " will now only allow command caller to assign roles"
                " to users with lower top role than theirs."
            )
        else:
            message = (
                "Commands for assigning and unassigning roles will now"
                " allow command caller to assign roles to any user."
            )
        await ctx.send(message)
