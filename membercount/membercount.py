from datetime import datetime

import discord
from redbot.core import commands


class MemberCount(commands.Cog):
    """Get count of all members + humans and bots separately."""

    @commands.command()
    async def membercount(self, ctx: commands.Context) -> None:
        """Get count of all members + humans and bots separately."""
        guild = ctx.guild
        member_count = 0
        human_count = 0
        bot_count = 0
        for member in guild.members:
            if member.bot:
                bot_count += 1
            else:
                human_count += 1
            member_count += 1
        if await ctx.embed_requested():
            embed = discord.Embed(
                timestamp=datetime.utcnow(), color=await ctx.embed_color()
            )
            embed.add_field(name="Members", value=str(member_count))
            embed.add_field(name="Humans", value=str(human_count))
            embed.add_field(name="Bots", value=str(bot_count))
            await ctx.send(embed=embed)
        else:
            await ctx.send(
                f"**Members:** {member_count}\n"
                f"**Humans:** {human_count}\n"
                f"**Bots:** {bot_count}"
            )
