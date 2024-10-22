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

import logging
import time
from io import BytesIO
from pathlib import Path
from typing import cast

import rlapi
from PIL import Image, ImageFile
from redbot.core import commands
from redbot.core.commands import NoParseOptional as Optional
from redbot.core.config import Value
from redbot.core.utils.views import SetApiView
from rlapi.ext.tier_breakdown.rlstatsnet import get_tier_breakdown

from .abc import MixinMeta
from .image import RLStatsImageTemplate

log = logging.getLogger("red.jackcogs.rlstats")


class SettingsMixin(MixinMeta):
    @commands.is_owner()
    @commands.group(name="rlset")
    async def rlset(self, ctx: commands.Context) -> None:
        """RLStats configuration options."""

    @rlset.command()
    async def credentials(self, ctx: commands.Context) -> None:
        """Instructions to set the Rocket League API credentials."""
        message = (
            "**Rocket League API is currently in closed beta"
            " and Psyonix doesn't give out access to it easily.**\n"
            "To request API access, you should contact Psyonix by email"
            " `RLPublicAPI@psyonix.com` and hope for positive response.\n\n"
            "When (and if) you get API access, copy your Client ID and Secret "
            "from your product's settings on Epic Games Developer Portal"
            " and click the button below to set your credentials."
        )
        await ctx.send(
            message,
            view=SetApiView(
                default_service="rocket_league",
                default_keys={"client_id": "", "client_secret": ""},
            ),
        )

    @rlset.command(name="updatebreakdown")
    async def updatebreakdown(self, ctx: commands.Context) -> None:
        """Force update tier breakdown before its expiry."""
        await ctx.send("Updating tier breakdown...")
        async with ctx.typing():
            msg = await self._force_update_breakdown()
        await ctx.send(msg)

    async def _force_update_breakdown(self) -> str:
        async with self.breakdown_lock:
            try:
                tier_breakdown = await get_tier_breakdown(self.rlapi_client)
            except rlapi.HTTPException as e:
                msg = "Could not download tier breakdown."
                log.warning(msg, exc_info=e)
                return msg
            except ValueError as e:
                msg = "Could not parse downloaded tier breakdown."
                log.warning(msg, exc_info=e)
                return msg

            now = time.time()
            self.rlapi_client.tier_breakdown = tier_breakdown
            self.breakdown_updated_at = now
            await self.config.tier_breakdown.set(tier_breakdown)
            await self.config.breakdown_updated_at.set(now)

            return "Tier breakdown updated."

    @rlset.group(name="image")
    async def rlset_bgimage(self, ctx: commands.Context) -> None:
        """Set background for stats image."""

    @rlset_bgimage.group(name="extramodes")
    async def rlset_bgimage_extramodes(self, ctx: commands.Context) -> None:
        """Options for background for extra modes stats image."""

    @rlset_bgimage_extramodes.command("set")
    async def rlset_bgimage_extramodes_set(self, ctx: commands.Context) -> None:
        """
        Set background for extra modes stats image.
        This command accepts only 1920x1080 images.

        Use `[p]rlset bgimage extramodes reset` to reset to default.
        """
        await self._rlset_bgimage_set(
            ctx, self.cog_data_path / "bgs/extramodes.png", self.extramodes_template
        )

    @rlset_bgimage_extramodes.command("reset")
    async def rlset_bgimage_extramodes_reset(self, ctx: commands.Context) -> None:
        """Reset background for extra modes stats image to default."""
        await self._rlset_bgimage_reset(
            ctx,
            "extra modes",
            self.cog_data_path / "bgs/extramodes.png",
            self.bundled_data_path / "bgs/extramodes.png",
            self.extramodes_template,
        )

    @rlset_bgimage_extramodes.command("overlay")
    async def rlset_bgimage_extramodes_overlay(
        self, ctx: commands.Context, percentage: Optional[int] = None
    ) -> None:
        """
        Set overlay percentage for extra modes stats image.

        Leave empty to reset to default (70%)
        """
        await self._rlset_bgimage_overlay(
            ctx,
            percentage,
            "extra modes",
            self.config.extramodes_overlay,
            self.extramodes_template,
        )

    @rlset_bgimage.group(name="competitive")
    async def rlset_bgimage_competitive(self, ctx: commands.Context) -> None:
        """Options for background for competitive stats image."""

    @rlset_bgimage_competitive.command("set")
    async def rlset_bgimage_competitive_set(self, ctx: commands.Context) -> None:
        """
        Set background for competitive stats image.
        This command accepts only 1920x1080 images.

        Use `[p]rlset bgimage competitive reset` to reset to default.
        """
        await self._rlset_bgimage_set(
            ctx, self.cog_data_path / "bgs/competitive.png", self.competitive_template
        )

    @rlset_bgimage_competitive.command("reset")
    async def rlset_bgimage_competitive_reset(self, ctx: commands.Context) -> None:
        """Reset background for competitive stats image to default."""
        await self._rlset_bgimage_reset(
            ctx,
            "competitive",
            self.cog_data_path / "bgs/competitive.png",
            self.bundled_data_path / "bgs/competitive.png",
            self.competitive_template,
        )

    @rlset_bgimage_competitive.command("overlay")
    async def rlset_bgimage_competitive_overlay(
        self, ctx: commands.Context, percentage: Optional[int] = None
    ) -> None:
        """
        Set overlay percentage for competitive stats image.

        Leave empty to reset to default (40%)
        """
        await self._rlset_bgimage_overlay(
            ctx,
            percentage,
            "competitive",
            self.config.competitive_overlay,
            self.competitive_template,
        )

    async def _rlset_bgimage_set(
        self, ctx: commands.Context, filename: Path, template: RLStatsImageTemplate
    ) -> None:
        if not ctx.message.attachments:
            await ctx.send("You have to send background image.")
            return
        if len(ctx.message.attachments) > 1:
            await ctx.send("You can send only one attachment.")
            return
        async with ctx.typing():
            a = ctx.message.attachments[0]
            fp = BytesIO()
            await a.save(fp)
            filename.parent.mkdir(parents=True, exist_ok=True)
            try:
                im = await self._run_in_executor(Image.open, fp)
            except IOError:
                await ctx.send("Attachment couldn't be open.")
                return
            if im.size != (1920, 1080):
                await ctx.send("Background image needs to be in 1920x1080 size.")
                return
            im = cast(
                ImageFile.ImageFile, await self._run_in_executor(im.convert, "RGBA")
            )
            await self._run_in_executor(im.save, filename, "PNG")
            template.bg_image = filename
        await ctx.send("Background image was successfully set.")

    async def _rlset_bgimage_reset(
        self,
        ctx: commands.Context,
        mode: str,
        custom_filename: Path,
        default_filename: Path,
        template: RLStatsImageTemplate,
    ) -> None:
        try:
            custom_filename.unlink()
        except FileNotFoundError:
            await ctx.send(
                f"There was no custom background set for {mode} stats image."
            )
        else:
            await ctx.send(
                f"Background for {mode} stats image is changed back to default."
            )
            template.bg_image = default_filename

    async def _rlset_bgimage_overlay(
        self,
        ctx: commands.Context,
        percentage: Optional[int],
        mode: str,
        value_obj: Value,
        template: RLStatsImageTemplate,
    ) -> None:
        if percentage is None:
            await value_obj.clear()
            template.bg_overlay = await value_obj()
            await ctx.send(f"Overlay percentage for {mode} stats image reset.")
            return
        if not 0 <= percentage <= 100:
            await ctx.send("Percentage value has to be in range 0-100.")
            return
        await value_obj.set(percentage)
        template.bg_overlay = percentage
        await ctx.send(f"Overlay percentage for {mode} stats set to {percentage}%")
