from .cogboard import CogBoard


def setup(bot):
    bot.add_cog(CogBoard(bot))
