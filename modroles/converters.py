import discord
from redbot.core import commands

from . import modroles


_RoleConverter = commands.RoleConverter()


class AssignableRoleConverter(discord.Role):
    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> discord.Role:
        modroles_cog = ctx.cog
        # *I hope* this won't break with our reload system
        if modroles_cog is None or modroles_cog.__class__ is not modroles.ModRoles:
            raise commands.BadArgument(
                "Converter was unable to access ModRoles config."
            )

        # class check above is not enough for mypy
        assert isinstance(modroles_cog, modroles.ModRoles), "mypy"

        role = await _RoleConverter.convert(ctx, argument)
        assignable_roles = await modroles_cog.config.guild(ctx.guild).assignable_roles()

        if role.id not in assignable_roles:
            raise commands.BadArgument(
                f"The provided role is not a valid assignable role."
            )
        return role
