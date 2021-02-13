import io
import asyncio
import contextlib
import logging
import math
import html
import os
import time


import discord
import random
from discord.ext import commands

from util import cache_system2
from util import codeforces_api as cf
from util import codeforces_common as cf_common
from util import discord_common
from util import events
from util import paginator
from util import table
from util import tasks
from util import db
import TLEconstants

from PIL import Image, ImageFont, ImageDraw

_HANDLES_PER_PAGE = 15
_NAME_MAX_LEN = 20
_PAGINATE_WAIT_TIME = 5 * 60  # 5 minutes
_PRETTY_HANDLES_PER_PAGE = 10
_TOP_DELTAS_COUNT = 10
_MAX_RATING_CHANGES_PER_EMBED = 15
_UPDATE_HANDLE_STATUS_INTERVAL = 6 * 60 * 60  # 6 hours


class HandleCogError(commands.CommandError):
    pass


def rating_to_color(rating):
    """returns (r, g, b) pixels values corresponding to rating"""
    # TODO: Integrate these colors with the ranks in codeforces_api.py
    BLACK = (10, 10, 10)
    RED = (255, 20, 20)
    BLUE = (0, 0, 200)
    GREEN = (0, 140, 0)
    ORANGE = (250, 140, 30)
    PURPLE = (160, 0, 120)
    CYAN = (0, 165, 170)
    GREY = (70, 70, 70)
    if rating is None or rating=='N/A':
        return BLACK
    if rating < 1200:
        return GREY
    if rating < 1400:
        return GREEN
    if rating < 1600:
        return CYAN
    if rating < 1900:
        return BLUE
    if rating < 2100:
        return PURPLE
    if rating < 2400:
        return ORANGE
    return RED

FONTS = [
    'Noto Sans',
    'Noto Sans CJK JP',
    'Noto Sans CJK SC',
    'Noto Sans CJK TC',
    'Noto Sans CJK HK',
    'Noto Sans CJK KR',
]

def _spaceit(word,sz):
    while len(word) < sz:
        word += " "
    while len(word) > sz:
        word = word[:-1]
    return word

def spaceit(arr):
    res = []
    gap = [3,15,10,15,6]
    for i in range(len(arr)):
        x = arr[i]
        y = gap[i]
        res.append(_spaceit(x,y))
    return res

def get_gudgitters_image(rankings):
    """return PIL image for rankings"""
    res = '```diff\n'
    res += ' '.join(spaceit(['#', 'Name', 'Rating','Handle', 'Points']))
    res += "\n"
    
    for i, (pos, name, handle, rating, score) in enumerate(rankings):
        res += ' '.join(spaceit([str(pos), f'{name}',f' ({rating if rating else "N/A"})', handle, str(score)]))
        res += "\n"
    res+="```"
    return res




def _make_profile_embed(member, user, *, mode):
    assert mode in ('set', 'get')
    if mode == 'set':
        desc = f'Handle for {member.mention} successfully set to **[{user.handle}]({user.url})**'
    else:
        desc = f'Handle for {member.mention} is currently set to **[{user.handle}]({user.url})**'
    if user.rating is None:
        embed = discord.Embed(description=desc)
        embed.add_field(name='Rating', value='Unrated', inline=True)
    else:
        embed = discord.Embed(description=desc, color=user.rank.color_embed)
        embed.add_field(name='Rating', value=user.rating, inline=True)
        embed.add_field(name='Rank', value=user.rank.title, inline=True)
    embed.set_thumbnail(url=f'https:{user.titlePhoto}')
    return embed




class Handles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)
        self.font = ImageFont.truetype(TLEconstants.NOTO_SANS_CJK_BOLD_FONT_PATH, size=26) # font for ;handle pretty

    @commands.Cog.listener()
    @discord_common.once
    async def on_ready(self):
        cf_common.event_sys.add_listener(self._on_rating_changes)
        self._set_ex_users_inactive_task.start()

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        cf_common.user_db.set_inactive([(member.guild.id, member.id)])


    @commands.Cog.listener()
    async def on_member_join(self, member):
        rc = cf_common.user_db.update_status(member.guild.id, [member.id])
        if rc == 1:
            handle = cf_common.user_db.get_handle(member.id, member.guild.id)
            await self._update_ranks(member.guild, [(int(member.id), handle)])

    @tasks.task_spec(name='SetExUsersInactive',
                     waiter=tasks.Waiter.fixed_delay(_UPDATE_HANDLE_STATUS_INTERVAL))
    async def _set_ex_users_inactive_task(self, _):
        # To set users inactive in case the bot was dead when they left.
        to_set_inactive = []
        for guild in self.bot.guilds:
            user_id_handle_pairs = cf_common.user_db.get_handles_for_guild(guild.id)
            to_set_inactive += [(guild.id, user_id) for user_id, _ in user_id_handle_pairs
                                if guild.get_member(user_id) is None]
        cf_common.user_db.set_inactive(to_set_inactive)

    @events.listener_spec(name='RatingChangesListener',
                          event_cls=events.RatingChangesUpdate,
                          with_lock=True)
    async def _on_rating_changes(self, event):
        contest, changes = event.contest, event.rating_changes
        change_by_handle = {change.handle: change for change in changes}

        async def update_for_guild(guild):
            if cf_common.user_db.has_auto_role_update_enabled(guild.id):
                with contextlib.suppress(HandleCogError):
                    await self._update_ranks_all(guild)
            channel_id = cf_common.user_db.get_rankup_channel(guild.id)
            channel = guild.get_channel(channel_id)
            if channel is not None:
                with contextlib.suppress(HandleCogError):
                    embeds = self._make_rankup_embeds(guild, contest, change_by_handle)
                    for embed in embeds:
                        await channel.send(embed=embed)

        await asyncio.gather(*(update_for_guild(guild) for guild in self.bot.guilds),
                             return_exceptions=True)
        self.logger.info(f'All guilds updated for contest {contest.id}.')

    @commands.group(brief='Commands that have to do with handles', invoke_without_command=True)
    async def handle(self, ctx):
        """Change or collect information about specific handles on Codeforces"""
        await ctx.send_help(ctx.command)

    @staticmethod
    async def update_member_rank_role(member, role_to_assign, *, reason):
        """Sets the `member` to only have the rank role of `role_to_assign`. All other rank roles
        on the member, if any, will be removed. If `role_to_assign` is None all existing rank roles
        on the member will be removed.
        """
        role_names_to_remove = {rank.title for rank in cf.RATED_RANKS}
        if role_to_assign is not None:
            role_names_to_remove.discard(role_to_assign.name)
            if role_to_assign.name not in ['Newbie', 'Pupil', 'Specialist', 'Expert']:
                role_names_to_remove.add('Purgatory')
        to_remove = [role for role in member.roles if role.name in role_names_to_remove]
        if to_remove:
            await member.remove_roles(*to_remove, reason=reason)
        if role_to_assign is not None and role_to_assign not in member.roles:
            await member.add_roles(role_to_assign, reason=reason)

    @handle.command(brief='Set Codeforces handle of a user')
    @commands.has_any_role('Admin', 'Moderator')
    async def set(self, ctx, member: discord.Member, handle: str):
        """Set Codeforces handle of a user."""
        # CF API returns correct handle ignoring case, update to it
        user, = await cf.user.info(handles=[handle])
        await self._set(ctx, member, user)
        embed = _make_profile_embed(member, user, mode='set')
        await ctx.send(embed=embed)

    async def _set(self, ctx, member, user):
        handle = user.handle
        cf_common.user_db.cache_cf_user(user)

        if user.rank == cf.UNRATED_RANK:
            role_to_assign = None
        else:
            roles = [role for role in ctx.guild.roles if role.name == user.rank.title]
            if not roles:
                raise HandleCogError(f'Role for rank `{user.rank.title}` not present in the server')
            role_to_assign = roles[0]
        await self.update_member_rank_role(member, role_to_assign,
                                           reason='New handle set for user')

    @handle.command(brief='Identify yourself', usage='[handle]')
    @cf_common.user_guard(group='handle',
                          get_exception=lambda: HandleCogError('Identification is already running for you'))
    async def identify(self, ctx, handle: str):
        """Link a codeforces account to discord account by submitting a compile error to a random problem"""

        if handle in cf_common.HandleIsVjudgeError.HANDLES:
            raise cf_common.HandleIsVjudgeError(handle)

        users = await cf.user.info(handles=[handle])
        invoker = str(ctx.author)
        handle = users[0].handle
        problems = [prob for prob in cf_common.cache2.problem_cache.problems
                    if prob.rating <= 1200]
        problem = random.choice(problems)
        await ctx.send(f'`{invoker}`, submit a compile error to <{problem.url}> within 60 seconds')
        await asyncio.sleep(60)

        subs = await cf.user.status(handle=handle, count=5)
        if any(sub.problem.name == problem.name and sub.verdict == 'COMPILATION_ERROR' for sub in subs):
            user, = await cf.user.info(handles=[handle])
            await self._set(ctx, ctx.author, user)
            embed = _make_profile_embed(ctx.author, user, mode='set')
            await ctx.send(embed=embed)
        else:
            await ctx.send(f'Sorry `{invoker}`, can you try again?')



    @handle.command(brief='Remove handle for a user')
    @commands.has_any_role('Admin', 'Moderator')
    async def remove(self, ctx, member: discord.Member):
        """Remove Codeforces handle of a user."""

        await self.update_member_rank_role(member, role_to_assign=None,
                                           reason='Handle removed for user')
        embed = discord_common.embed_success(f'Removed handle for {member.mention}')
        await ctx.send(embed=embed)

    

    @discord_common.send_error_if(HandleCogError, cf_common.HandleIsVjudgeError)
    async def cog_command_error(self, ctx, error):
        pass


def setup(bot):
    bot.add_cog(Handles(bot))
