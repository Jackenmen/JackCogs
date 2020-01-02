import discord

from redbot.core import commands


class AssignableRoleConverter(commands.RoleConverter):
    async def convert(self, ctx, argument) -> discord.Role:
        modroles_cog = ctx.command.cog
        if modroles_cog is None:
            raise commands.BadArgument("The ModRoles cog is not loaded.")

        role = await super().convert(ctx, argument)
        assignable_roles = await modroles_cog.config.guild(ctx.guild).assignable_roles()

        if role.id not in assignable_roles:
            raise commands.BadArgument(
                f"The provided role is not a valid assignable role."
            )
        return role
