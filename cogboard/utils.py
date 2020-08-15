from copy import copy

from redbot.core import commands


async def get_fake_context(
    ctx: commands.Context, command: commands.Command
) -> commands.Context:
    fake_message = copy(ctx.message)
    fake_message.content = f"{ctx.prefix}{command.qualified_name}"
    return await ctx.bot.get_context(fake_message)
