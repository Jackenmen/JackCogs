import discord
from redbot.core import commands, checks
from redbot.core.bot import Red
from redbot.core.config import Config
from redbot.core.utils.chat_formatting import box
from redbot.core.utils.mod import is_mod_or_superior

from .converters import AssignableRoleConverter as AssignableRole


class ModRoles(commands.Cog):
    """Allow moderators to assign configured roles to users."""

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=176070082584248320, force_registration=True
        )
        self.config.register_guild(assignable_roles=[])

    async def _assign_checks(
        self, ctx: commands.Context, member: discord.Member
    ) -> bool:
        if await self.bot.is_owner(ctx.author):
            return True
        if ctx.author.id in {ctx.guild.owner.id, member.id}:
            return True
        if ctx.guild.me == member:
            await ctx.send("Pfft, you can't apply roles to me.")
            return False
        if ctx.author.top_role <= member.top_role:
            await ctx.send(
                "You can't assign roles to member whose top role is higher than yours."
            )
            return False
        if await is_mod_or_superior(self.bot, member):
            await ctx.send("You can't assign roles to member who is mod or higher.")
            return False
        return True

    @commands.command()
    @commands.guild_only()
    @checks.mod_or_permissions(manage_roles=True)
    async def assignrole(
        self, ctx: commands.Context, role: AssignableRole, *, member: discord.Member
    ) -> None:
        """
        Assign a role to a member.

        NOTE: The role is case sensitive!
        """
        if not await self._assign_checks(ctx, member):
            return
        try:
            await member.add_roles(role)
        except discord.Forbidden:
            if ctx.guild.me.top_role <= role:
                await ctx.send(
                    f"I tried to add {role.name} to {member.display_name} but"
                    " that role is higher than my highest role in the Discord hierarchy"
                    " so I was unable to successfully add it."
                )
            else:
                await ctx.send(
                    "I attempted to do something that Discord denied me"
                    " permissions for. Your command failed to successfully complete."
                )
        else:
            await ctx.send(f"Role {role.name} added to {member.display_name}")

    @commands.command()
    @commands.guild_only()
    @checks.mod_or_permissions(manage_roles=True)
    async def unassignrole(
        self, ctx: commands.Context, role: AssignableRole, *, member: discord.Member
    ) -> None:
        """
        Unassign a role from a member.

        NOTE: The role is case sensitive!
        """
        if not await self._assign_checks(ctx, member):
            return
        try:
            await member.remove_roles(role)
        except discord.Forbidden:
            if ctx.guild.me.top_role <= role:
                await ctx.send(
                    f"I tried to remove {role.name} from {member.display_name} but"
                    " that role is higher than my highest role in the Discord hierarchy"
                    " so I was unable to successfully add it."
                )
            else:
                await ctx.send(
                    "I attempted to do something that Discord denied me"
                    " permissions for. Your command failed to successfully complete."
                )
        else:
            await ctx.send(f"Role {role.name} removed from {member.display_name}")

    @commands.group()
    @commands.guild_only()
    @checks.admin_or_permissions(manage_roles=True)
    async def modroles(self, ctx: commands.Context) -> None:
        """Settings for assignable roles"""

    @modroles.command(name="add")
    async def modroles_add(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Add assignable role."""
        conf_group = self.config.guild(ctx.guild).assignable_roles
        assignable_roles = await conf_group()
        if role.id in assignable_roles:
            return await ctx.send("This role is already assignable.")
        assignable_roles.append(role.id)
        await conf_group.set(assignable_roles)
        await ctx.send(f"Role {role.name} added to assignable roles.")

    @modroles.command(name="remove")
    async def modroles_remove(
        self, ctx: commands.Context, *, role: AssignableRole
    ) -> None:
        """Remove assignable role."""
        async with self.config.guild(ctx.guild).assignable_roles() as assignable_roles:
            assignable_roles.remove(role.id)
        await ctx.send(f"Role {role.name} removed from assignable roles.")

    @modroles.command(name="list")
    async def modroles_list(self, ctx: commands.Context) -> None:
        assignable_roles = set(await self.config.guild(ctx.guild).assignable_roles())
        valid_roles = tuple(r for r in ctx.guild.roles if r.id in assignable_roles)
        valid_roles_ids = set(r.id for r in valid_roles)

        if assignable_roles != valid_roles_ids:
            await self.config.guild(ctx.guild).assignable_roles.set(valid_roles_ids)

        fmt_assignable_roles = "\n".join([f"+ {r.name}" for r in valid_roles])

        await ctx.send(
            box(f"Available assignable roles:\n{fmt_assignable_roles}", "diff")
        )
