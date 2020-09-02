# Copyright 2018-2020 Jakub Kuczys (https://github.com/jack1142)
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

from copy import copy

from redbot.core import commands


async def get_fake_context(
    ctx: commands.Context, command: commands.Command
) -> commands.Context:
    fake_message = copy(ctx.message)
    fake_message.content = f"{ctx.prefix}{command.qualified_name}"
    return await ctx.bot.get_context(fake_message)
