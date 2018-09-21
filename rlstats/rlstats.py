import discord
from discord.ext import commands

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import os
from .utils import checks
from .utils.dataIO import fileIO
import math
from collections import defaultdict
import logging

try:
    from PIL import Image, ImageDraw, ImageFont, ImageColor, ImageOps
except:
    raise RuntimeError("Can't load pillow. Do 'pip3 install pillow'.")

try:
    from babel.numbers import format_decimal
except:
    raise RuntimeError("Can't load Babel. Do 'pip3 install Babel'.")

log = logging.getLogger('red.rlstats')


class RLStats:
    """Get your Rocket League stats with a single command!"""
    # TODO:
    # move rltracker cog functions to this cog
    # rest of TODO in rlstats method

    def __init__(self, bot):
        self.bot = bot
        self.check_folders()
        self.settings = fileIO("data/rlstats/settings.json", "load")
        self.session = aiohttp.ClientSession()
        self.ranks = (
            'Unranked',
            'Bronze I',
            'Bronze II',
            'Bronze III',
            'Silver I',
            'Silver II',
            'Silver III',
            'Gold I',
            'Gold II',
            'Gold III',
            'Platinum I',
            'Platinum II',
            'Platinum III',
            'Diamond I',
            'Diamond II',
            'Diamond III',
            'Champion I',
            'Champion II',
            'Champion III',
            'Grand Champion'
        )
        self.offsets = {
            10: (0, 0),
            11: (960, 0),
            12: (0, 383),
            13: (960, 383)
        }
        self.coords = {
            'username': (960, 71),
            'rank_image': (153, 248),
            'rank_text': (242, 453),  # center of rank text
            'matches_played': (822, 160),
            'win_streak': (492, 216),
            'skill': (729, 272),
            'gain': (715, 328),
            'div_down': (552, 384),
            'div_up': (727, 384),
            'tier_down': (492, 446),
            'tier_up': (667, 446),
            'rewards': (914, 921)
        }
        self.rank_size = (179, 179)
        self.tier_size = (49, 49)

    def __unload(self):
        self.session.close()

    def check_folders(self):
        if not os.path.exists("data/rlstats"):
            print("Creating data/rlstats folder...")
            os.makedirs("data/rlstats")

        if not os.path.exists("data/rlstats/temp"):
            print("Creating data/rlstats/temp folder...")
            os.makedirs("data/rlstats/temp")

        self.check_files()

    def check_files(self):
        if not os.path.isfile("data/rlstats/settings.json"):
            default = {
                "USERS": {},
                "token": ""
            }
            print("Creating default rlstats settings.json...")
            fileIO("data/rlstats/settings.json", "save", default)

        if not os.path.isfile("data/rlstats/rank_tiers.json"):
            self.rank_tiers = None
            print("Creating rank_tiers.json...")
            self.bot.loop.create_task(self._get_tier_breakdown())
        else:
            self.rank_tiers = self._fix_numbers_dict(fileIO("data/rlstats/rank_tiers.json", "load"))

    def _add_coords(self, coords1, coords2):
        """Adds two tuples with coordinates (x,y)"""
        x = coords1[0] + coords2[0]
        y = coords1[1] + coords2[1]
        return (x, y)

    def _get_coords(self, playlist_id, coords_name):
        """Gets coords for given element in chosen playlist"""
        coords = self.coords[coords_name]
        offset = self.offsets[playlist_id]
        return self._add_coords(coords, offset)

    async def _find_steam_profile(self, id):
        """Find steam profile by SteamID64 or custom url"""
        try:
            async with self.session.get('https://steamcommunity.com/profiles/{}/?xml=1'.format(id)) as resp:
                steam_profile = ET.fromstring(await resp.text())
        except aiohttp.ClientResponseError:
            await self.bot.say(
                "An error occured while searching for Steam profile. "
                "If this will happen again, please inform bot owner about the issue."
            )
            raise
        except aiohttp.ClientError:
            await self.bot.say(
                "An error occured while searching for Steam profile. "
                "If this will happen again, please inform bot owner about the issue."
            )
            raise
        error = steam_profile.find('error')

        if error is None:
            pass
        elif error.text == 'The specified profile could not be found.':
            try:
                async with self.session.get('https://steamcommunity.com/id/{}/?xml=1'.format(id)) as resp:
                    steam_profile = ET.fromstring(await resp.text())
            except aiohttp.ClientResponseError:
                await self.bot.say(
                    "An error occured while searching for Steam profile. "
                    "If this will happen again, please inform bot owner about the issue."
                )
                raise
            except aiohttp.ClientError:
                await self.bot.say(
                    "An error occured while searching for Steam profile. "
                    "If this will happen again, please inform bot owner about the issue."
                )
                raise
            error = steam_profile.find('error')

            if error is None:
                id = steam_profile.find('steamID64').text
            else:
                log.debug(
                    "Steam threw error while searching profile by custom url: {}".format(error.text)
                )
                return None
        else:
            log.debug(
                "Steam threw error while searching profile by ID: {}".format(error.text)
            )
            return None

    def _fix_numbers_dict(self, d: dict):
        """Converts (recursively) dictionary's keys with numbers to integers"""
        new = {}
        for k, v in d.items():
            if isinstance(v, dict):
                v = self._fix_numbers_dict(v)
            elif isinstance(v, list):
                v = self._fix_numbers_list(v)
            new[int(k)] = v
        return new

    def _fix_numbers_list(self, l: list):
        """Converts (recursively) list's values with numbers to floats"""
        new = []
        for v in l:
            if isinstance(v, dict):
                v = self._fix_numbers_dict(v)
            elif isinstance(v, list):
                v = self._fix_numbers_list(v)
            new.append(float(v))
        return new

    @checks.is_owner()
    @commands.group(pass_context=True, name="rlset")
    async def rlset(self, ctx):
        """Commands for setting Rocket League API settings.
        You can obtain your user token by
        requesting for API access in a ticket on https://support.rocketleague.com
        Under "Issue" you need to select Installation and setup > I need API access"""
        if ctx.invoked_subcommand is None:
            print(type(ctx.message.channel))
            await self.bot.send_cmd_help(ctx)

    @checks.is_owner()
    @rlset.command(pass_context=True, name="token")
    async def set_token(self, ctx, token):
        """Sets the user token. USE THIS COMMAND IN PM"""
        if ctx.message.channel.is_private:
            self.settings["token"] = token
            fileIO("data/rlstats/settings.json", "save", self.settings)
            await self.bot.say("User token set successfully! You should probably remove your message with token for safety.")
        else:
            await self.bot.delete_message(ctx.message)
            await self.bot.say("You can't set token from server channel! Use this command in PM instead.")

    @commands.command(pass_context=True)
    async def rlstats(self, ctx, id=None):
        """Checks for your or given player's Rocket League stats"""
        # TODO:
        # add support for PS4 and Xbox (there's no endpoint for Switch)
        # when there are multiple platforms available for given user, ask for platform in reaction menu
        # handle not-existing account IDs (preferably check if account exist at all and also if it exists in RL)
        # add number of wins (there's no text right now, only bars)
        # make Tier and division estimates shorter (create some additional methods)
        if 'token' not in list(self.settings.keys()) or self.settings['token'] == "":
            await self.bot.say(
                "`This cog wasn't configured properly. If you're the owner, setup the cog using {}rlset`".format(ctx.prefix)
            )
        else:
            await self.bot.send_typing(ctx.message.channel)

            if id is None:
                if ctx.message.author.id in self.settings['USERS']:
                    id = self.settings['USERS'][ctx.message.author.id]
                else:
                    await self.bot.say((
                        "Your Steam account is not connected with Discord. "
                        "If you want to get stats, either give Steam ID after a command: "
                        "`{0}rlstats <SteamID64>/<customURL>`"
                        " or connect your account using command: "
                        "`{0}rlconnect <SteamID64>/<customURL>`"
                    ).format(ctx.prefix))
                    return
            else:
                converter = commands.MemberConverter(ctx, id)
                try:
                    member = converter.convert()
                    if member.id in self.settings['USERS']:
                        id = self.settings['USERS'][member.id]
                    else:
                        await self.bot.say((
                            "This user hasn't connected his Steam account with Discord. "
                            "You need to search for his stats using Steam ID: "
                            "`{0}rlstats <SteamID64>/<customURL>`"
                        ).format(ctx.prefix))
                        return
                except commands.errors.BadArgument:
                    steam_id = await self._find_steam_profile(id)
                    if steam_id is None:
                        await self.bot.say('The specified profile could not be found.')
                        return
                    else:
                        id = steam_id

            try:
                async with self.session.get(
                    'https://api.rocketleague.com/api/v1/steam/playerskills/{}/'.format(id),
                    headers={
                        'Authorization': 'Token {}'.format(self.settings['token'])
                    }
                ) as resp:
                    player = await resp.json()
            except aiohttp.ClientResponseError:
                await self.bot.say(
                    "An error occured while checking Rocket League Stats. "
                    "If this will happen again, please inform bot owner about the issue."
                )
                raise
            except aiohttp.ClientError:
                await self.bot.say(
                    "An error occured while checking Rocket League Stats. "
                    "If this will happen again, please inform bot owner about the issue."
                )
                raise

            player_skills = {}
            for playlist in player[0]['player_skills']:
                player_skills[playlist['playlist']] = playlist
            for playlist_id in range(10, 14):
                if playlist_id not in player_skills:
                    player_skills[playlist_id] = {
                        "division": 0,
                        "playlist": playlist_id,
                        "mu": 25,
                        "win_streak": 0,
                        "tier": 0,
                        "skill": 600,
                        "sigma": 8.333,
                        "matches_played": 0,
                        "tier_max": 19
                    }
            if 0 not in player_skills:
                player_skills[0] = {
                    "mu": 25,
                    "playlist": playlist_id,
                    "sigma": 8.333
                }
            if not player[0]['season_rewards']:
                player[0]['season_rewards'] = {
                    "wins": 0,
                    "level": 0
                }

            divisions = ('I', 'II', 'III', 'IV')
            bg_color = (255, 255, 255, 0)
            size = (1920, 1080)
            result = Image.new('RGBA', size, bg_color)
            process = Image.new('RGBA', size, bg_color)
            bg_image = Image.open('data/rlstats/rank_bg.png').convert('RGBA')
            result.paste(bg_image, (0, 0))
            draw = ImageDraw.Draw(process)

            fonts = {}
            fonts["RobotoCondensedBold90"] = ImageFont.truetype("data/rlstats/fonts/RobotoCondensedBold.ttf", 90)
            fonts["RobotoBold45"] = ImageFont.truetype("data/rlstats/fonts/RobotoBold.ttf", 45)
            fonts["RobotoLight45"] = ImageFont.truetype("data/rlstats/fonts/RobotoLight.ttf", 45)

            # Draw - username
            w, h = fonts["RobotoCondensedBold90"].getsize(player[0]["user_name"])
            coords = self._add_coords(self.coords['username'], (-w/2, -h/2))
            draw.text(coords, player[0]["user_name"],
                      font=fonts["RobotoCondensedBold90"], fill="white")

            # Draw - rank details
            for playlist_id in range(10, 14):
                # Draw - rank image
                temp = Image.new('RGBA', size, bg_color)
                temp_image = Image.open('data/rlstats/images/ranks/{}.png'.format(player_skills[playlist_id]['tier'])).convert('RGBA')
                temp_image.thumbnail(self.rank_size, Image.ANTIALIAS)
                coords = self._get_coords(playlist_id, 'rank_image')
                temp.paste(temp_image, coords)
                process = Image.alpha_composite(process, temp)
                draw = ImageDraw.Draw(process)

                # Draw - rank name (e.g. Diamond 3 Div 1)
                if player_skills[playlist_id]['tier']:
                    rank_text = self.ranks[int(player_skills[playlist_id]['tier'])]
                    if player_skills[playlist_id]['tier'] != player_skills[playlist_id]['tier_max']:
                        rank_text += " Div {}".format(divisions[int(player_skills[playlist_id]['division'])])
                else:
                    rank_text = "Unranked"

                w, h = fonts["RobotoLight45"].getsize(rank_text)
                coords = self._get_coords(playlist_id, 'rank_text')
                coords = self._add_coords(coords, (-w/2, -h/2))
                draw.text(coords, rank_text, font=fonts["RobotoLight45"], fill="white")

                # Draw - matches played
                coords = self._get_coords(playlist_id, 'matches_played')
                draw.text(coords, str(player_skills[playlist_id]['matches_played']), font=fonts["RobotoBold45"], fill="white")

                # Draw - Win/Losing Streak
                if player_skills[playlist_id]['win_streak'] < 0:
                    text = "Losing Streak:"
                else:
                    text = "Win Streak:"
                w, h = fonts["RobotoLight45"].getsize(text)
                coords_text = self._get_coords(playlist_id, 'win_streak')
                coords_amount = self._add_coords(coords_text, (11+w, 0))
                # Draw - "Win Streak" or "Losing Streak"
                draw.text(coords_text, text, font=fonts["RobotoLight45"], fill="white")
                # Draw - amount of won/lost games
                draw.text(coords_amount, str(player_skills[playlist_id]['win_streak']), font=fonts["RobotoBold45"], fill="white")

                # Draw - Skill Rating
                coords = self._get_coords(playlist_id, 'skill')
                draw.text(coords, str(player_skills[playlist_id]['skill']), font=fonts["RobotoBold45"], fill="white")

                # Draw - Gain/Loss
                if os.path.isfile('data/rltracker/{}_{}.txt'.format(id, playlist_id)):
                    with open('data/rltracker/{}_{}.txt'.format(id, playlist_id)) as file:
                        lines = file.readlines()
                        before = lines[-2].split(";")[3]
                        after = lines[-1].split(";")[3]
                        if before == "Mu":
                            gain = 0
                        else:
                            gain = abs((float(after) - float(before))*20)
                else:
                    gain = 0

                coords = self._get_coords(playlist_id, 'gain')
                if gain == 0:
                    draw.text(coords, "N/A", font=fonts["RobotoBold45"], fill="white")
                else:
                    draw.text(coords, str(format_decimal((gain), format='#.###', locale='pl_PL')), font=fonts["RobotoBold45"], fill="white")

                # Draw - Tier and division estimates
                if player_skills[playlist_id]['tier'] == 0:
                    # Draw - Division Down
                    coords = self._get_coords(playlist_id, 'div_down')
                    draw.text(coords, "N/A", font=fonts["RobotoBold45"], fill="white")

                    # Draw - Tier Down
                    # Icon
                    tier_down_temp = Image.new('RGBA', size, bg_color)
                    tier_down_image = Image.open('data/rlstats/images/ranks/0.png').convert('RGBA')
                    tier_down_image.thumbnail(self.tier_size, Image.ANTIALIAS)
                    coords_image = self._get_coords(playlist_id, 'tier_down')
                    tier_down_temp.paste(tier_down_image, coords_image)
                    process = Image.alpha_composite(process, tier_down_temp)
                    draw = ImageDraw.Draw(process)
                    # Points
                    coords_text = self._add_coords(coords_image, (self.tier_size[0]+11, -5))
                    draw.text(coords_text, "N/A", font=fonts["RobotoBold45"], fill="white")

                    # Draw - Division Up
                    coords = self._get_coords(playlist_id, 'div_up')
                    draw.text(coords, "N/A", font=fonts["RobotoBold45"], fill="white")

                    # Draw - Tier Up
                    # Icon
                    tier_up_temp = Image.new('RGBA', size, bg_color)
                    tier_up_image = Image.open('data/rlstats/images/ranks/0.png').convert('RGBA')
                    tier_up_image.thumbnail(self.tier_size, Image.ANTIALIAS)
                    coords_image = self._get_coords(playlist_id, 'tier_up')
                    tier_up_temp.paste(tier_up_image, coords_image)
                    process = Image.alpha_composite(process, tier_up_temp)
                    draw = ImageDraw.Draw(process)
                    # Points
                    coords_text = self._add_coords(coords_image, (self.tier_size[0]+11, -5))
                    draw.text(coords_text, "N/A", font=fonts["RobotoBold45"], fill="white")
                else:
                    # Draw - Division and Tier Down
                    if not player_skills[playlist_id]['tier'] == 1:
                        # Draw - Division Down
                        coords = self._get_coords(playlist_id, 'div_down')
                        if not player_skills[playlist_id]['division'] == 0:
                            difference = int(math.ceil(player_skills[playlist_id]['skill'] - self.rank_tiers[playlist_id][player_skills[playlist_id]['tier']-1][player_skills[playlist_id]['division']][0]))
                            if difference < 0:
                                difference = 0
                            draw.text(coords, "-" + str(difference), font=fonts["RobotoBold45"], fill="white")
                        else:
                            draw.text(coords, "N/A", font=fonts["RobotoBold45"], fill="white")

                        # Draw - Tier Down
                        # Icon
                        tier_down = 'data/rlstats/images/ranks/{}.png'.format(int(player_skills[playlist_id]['tier'])-1)
                        tier_down_temp = Image.new('RGBA', size, bg_color)
                        tier_down_image = Image.open(tier_down).convert('RGBA')
                        tier_down_image.thumbnail(self.tier_size, Image.ANTIALIAS)
                        coords_image = self._get_coords(playlist_id, 'tier_down')
                        tier_down_temp.paste(tier_down_image, coords_image)
                        process = Image.alpha_composite(process, tier_down_temp)
                        draw = ImageDraw.Draw(process)
                        # Points
                        difference = int(math.ceil(player_skills[playlist_id]['skill'] - self.rank_tiers[playlist_id][player_skills[playlist_id]['tier']-1][0][0]))
                        if difference < 0:
                            difference = 0
                        coords_text = self._add_coords(coords_image, (self.tier_size[0]+11, -5))
                        draw.text(coords_text, "N/A", font=fonts["RobotoBold45"], fill="white")
                    else:
                        # Draw - Division Down
                        coords = self._get_coords(playlist_id, 'div_down')
                        draw.text(coords, "N/A", font=fonts["RobotoBold45"], fill="white")

                        # Draw - Tier Down
                        # Icon
                        tier_down_temp = Image.new('RGBA', size, bg_color)
                        tier_down_image = Image.open('data/rlstats/images/ranks/0.png').convert('RGBA')
                        tier_down_image.thumbnail(self.tier_size, Image.ANTIALIAS)
                        coords_image = self._get_coords(playlist_id, 'tier_down')
                        tier_down_temp.paste(tier_down_image, coords_image)
                        process = Image.alpha_composite(process, tier_down_temp)
                        draw = ImageDraw.Draw(process)
                        # Points
                        coords_text = self._add_coords(coords_image, (self.tier_size[0]+11, -5))
                        draw.text(coords_text, "N/A", font=fonts["RobotoBold45"], fill="white")

                    # Draw - Division and Tier Up
                    if player_skills[playlist_id]['tier'] != player_skills[playlist_id]['tier_max']:
                        # Draw - Division Up
                        difference = int(math.ceil(self.rank_tiers[playlist_id][player_skills[playlist_id]['tier']-1][player_skills[playlist_id]['division']][1] - player_skills[playlist_id]['skill']))
                        if difference < 0:
                            difference = 0
                        coords = self._get_coords(playlist_id, 'div_up')
                        draw.text(coords, "+" + str(difference), font=fonts["RobotoBold45"], fill="white")

                        # Draw - Tier Up
                        # Icon
                        tier_up = 'data/rlstats/images/ranks/{}.png'.format(int(player_skills[playlist_id]['tier'])+1)
                        tier_up_temp = Image.new('RGBA', size, bg_color)
                        tier_up_image = Image.open(tier_up).convert('RGBA')
                        tier_up_image.thumbnail(self.tier_size, Image.ANTIALIAS)
                        coords_image = self._get_coords(playlist_id, 'tier_up')
                        tier_up_temp.paste(tier_up_image, coords_image)
                        process = Image.alpha_composite(process, tier_up_temp)
                        draw = ImageDraw.Draw(process)
                        # Points
                        difference = int(math.ceil(self.rank_tiers[playlist_id][player_skills[playlist_id]['tier']-1][3][1] - player_skills[playlist_id]['skill']))
                        if difference < 0:
                            difference = 0
                        coords_text = self._add_coords(coords_image, (self.tier_size[0]+11, -5))
                        draw.text(coords_text, "+" + str(difference), font=fonts["RobotoBold45"], fill="white")
                    else:
                        # Draw - Division Up
                        coords = self._get_coords(playlist_id, 'div_up')
                        draw.text(coords, "N/A", font=fonts["RobotoBold45"], fill="white")

                        # Draw - Tier Up
                        # Icon
                        tier_up_temp = Image.new('RGBA', size, bg_color)
                        tier_up_image = Image.open('data/rlstats/images/ranks/0.png').convert('RGBA')
                        tier_up_image.thumbnail(self.tier_size, Image.ANTIALIAS)
                        coords_image = self._get_coords(playlist_id, 'tier_up')
                        tier_up_temp.paste(tier_up_image, coords_image)
                        process = Image.alpha_composite(process, tier_up_temp)
                        draw = ImageDraw.Draw(process)
                        # Points
                        coords_text = self._add_coords(coords_image, (self.tier_size[0]+11, -5))
                        draw.text(coords_text, "N/A", font=fonts["RobotoBold45"], fill="white")

            # Season Reward Level
            reward_images = ['Unranked', 'Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond', 'Champion', 'GrandChampion']

            highest_rank = []
            for playlist_id in range(10, 14):
                highest_rank.append(player_skills[playlist_id]['tier'])
            highest_rank = max(highest_rank)
            highest_rank = player_skills[10]['tier']
            if player[0]['season_rewards']['level'] == 7:
                reward_ready = ""
            elif player[0]['season_rewards']['level'] * 3 < highest_rank:
                reward_ready = "Ready"
            else:
                reward_ready = "NotReady"

            reward_temp = Image.new('RGBA', size, bg_color)
            reward_image = Image.open('data/rlstats/images/rewards/{}{}.png'.format(reward_images[(0 if (0 if player[0]['season_rewards']['level'] is None else player[0]['season_rewards']['level']) is None else (0 if player[0]['season_rewards']['level'] is None else player[0]['season_rewards']['level']))], reward_ready)).convert('RGBA')
            reward_temp.paste(reward_image, (150, 886))
            process = Image.alpha_composite(process, reward_temp)
            draw = ImageDraw.Draw(process)
            # Season Reward Bars
            if reward_ready != "":
                reward_bars_win_image = Image.open('data/rlstats/images/rewards/bars/Bar{}Win.png'.format(reward_images[(0 if player[0]['season_rewards']['level'] is None else player[0]['season_rewards']['level'])])).convert('RGBA')
                if reward_ready == "Ready":
                    reward_bars_nowin_image = Image.open('data/rlstats/images/rewards/bars/Bar{}NoWin.png'.format(reward_images[(0 if player[0]['season_rewards']['level'] is None else player[0]['season_rewards']['level'])])).convert('RGBA')
                elif reward_ready == "NotReady":
                    reward_bars_nowin_image = Image.open('data/rlstats/images/rewards/bars/BarRed.png').convert('RGBA')
                for win in range(0, 10):
                    reward_bars_temp = Image.new('RGBA', size, bg_color)
                    coords = self._add_coords(self.coords['rewards'], (win*83, 0))
                    if (0 if player[0]['season_rewards']['wins'] is None else player[0]['season_rewards']['wins']) > win:
                        reward_bars_temp.paste(reward_bars_win_image, coords)
                    else:
                        reward_bars_temp.paste(reward_bars_nowin_image, coords)
                    process = Image.alpha_composite(process, reward_bars_temp)
                    draw = ImageDraw.Draw(process)

            # save result
            result = Image.alpha_composite(result, process)
            result.save('data/rlstats/temp/{}_profile.png'.format(id), 'PNG', quality=100)
            await self.bot.send_file(
                ctx.message.channel,
                'data/rlstats/temp/{}_profile.png'.format(id),
                content='Rocket League Stats for **{}** _(arrows show amount of points for division down/up)_'.format(player[0]["user_name"])
            )
            os.remove('data/rlstats/temp/{}_profile.png'.format(id))

    @commands.command(pass_context=True)
    async def rlconnect(self, ctx, id):
        """Connects Steam account with Discord. Use SteamID64 or custom url."""
        steam_id = self._find_steam_profile(id)
        if steam_id is None:
            await self.bot.say(
                'The specified profile could not be found. '
                'I did not connect your Steam account with Discord.'
            )
            return
        else:
            id = steam_id

        self.settings["USERS"][ctx.message.author.id] = id
        fileIO("data/rlstats/settings.json", "save", self.settings)
        await self.bot.say("You successfully connected your Steam account with Discord!")

    async def _get_tier_breakdown(self):
        # {10:{},11:{},12:{},13:{}}
        self.rank_tiers = defaultdict(lambda: defaultdict(dict))

        for i in range(19):
            try:
                async with self.session.get('http://rltracker.pro/tier_breakdown/get_division_stats?tier_id={}'.format(i+1)) as resp:
                    tier = await resp.json()
            except aiohttp.ClientResponseError:
                log.error('Downloading tier breakdown did not succeed.')
                raise
            except aiohttp.ClientError:
                log.error('Downloading tier breakdown did not succeed.')
                raise

            for breakdown in tier:
                self.rank_tiers[breakdown['playlist_id']][i][breakdown['division']] = [breakdown['from'], breakdown['to']]

        fileIO("data/rlstats/rank_tiers.json", "save", self.rank_tiers)

    @checks.is_owner()
    @rlset.command(pass_context=True, name="updatebreakdown")
    async def updatebreakdown(self, ctx):
        """Update tier breakdown"""
        await self.bot.say("Updating tier breakdown...")
        await self._get_tier_breakdown()
        await self.bot.say("Tier breakdown updated.")


def setup(bot):
    bot.add_cog(RLStats(bot))
