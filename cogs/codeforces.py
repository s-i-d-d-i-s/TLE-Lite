import datetime
import random
from typing import List
import math
import time
from collections import defaultdict

import discord
from discord.ext import commands

from util import codeforces_api as cf
from util import codeforces_common as cf_common
from util import discord_common

from util import paginator
from util import cache_system2



class CodeforcesCogError(commands.CommandError):
    pass


class Codeforces(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.converter = commands.MemberConverter()



    # @commands.command(brief='Recommend a problem', usage='[tags...] [rating]')
    # @cf_common.user_guard(group='gitgud')
    # async def gimme(self, ctx, *args):
    #     handle, = await cf_common.resolve_handles(ctx, self.converter, ('!' + str(ctx.author),))
    #     rating = round(cf_common.user_db.fetch_cf_user(handle).effective_rating, -2)
    #     tags = []
    #     for arg in args:
    #         if arg.isdigit():
    #             rating = int(arg)
    #         else:
    #             tags.append(arg)

    #     submissions = await cf.user.status(handle=handle)
    #     solved = {sub.problem.name for sub in submissions if sub.verdict == 'OK'}

    #     problems = [prob for prob in cf_common.cache2.problem_cache.problems
    #                 if prob.rating == rating and prob.name not in solved and
    #                 not cf_common.is_contest_writer(prob.contestId, handle)]
    #     if tags:
    #         problems = [prob for prob in problems if prob.tag_matches(tags)]

    #     if not problems:
    #         raise CodeforcesCogError('Problems not found within the search parameters')

    #     problems.sort(key=lambda problem: cf_common.cache2.contest_cache.get_contest(
    #         problem.contestId).startTimeSeconds)

    #     choice = max([random.randrange(len(problems)) for _ in range(2)])
    #     problem = problems[choice]

    #     title = f'{problem.index}. {problem.name}'
    #     desc = cf_common.cache2.contest_cache.get_contest(problem.contestId).name
    #     embed = discord.Embed(title=title, url=problem.url, description=desc)
    #     embed.add_field(name='Rating', value=problem.rating)
    #     if tags:
    #         tagslist = ', '.join(problem.tag_matches(tags))
    #         embed.add_field(name='Matched tags', value=tagslist)
    #     await ctx.send(f'Recommended problem for `{handle}`', embed=embed)



    @commands.command(brief='List solved problems',
                      usage='[handles] [+hardest] [+practice] [+contest] [+virtual] [+outof] [+team] [+tag..] [r>=rating] [r<=rating] [d>=[[dd]mm]yyyy] [d<[[dd]mm]yyyy] [c+marker..] [i+index..]')
    async def stalk(self, ctx, *args):
        """Print problems solved by user sorted by time (default) or rating.
        All submission types are included by default (practice, contest, etc.)
        """
        (hardest,), args = cf_common.filter_flags(args, ['+hardest'])
        filt = cf_common.SubFilter(False)
        args = filt.parse(args)
        handles = args
        handles = await cf_common.resolve_handles(ctx, self.converter, handles)
        submissions = [await cf.user.status(handle=handle) for handle in handles]
        submissions = [sub for subs in submissions for sub in subs]
        submissions = filt.filter_subs(submissions)

        if not submissions:
            raise CodeforcesCogError('Submissions not found within the search parameters')

        if hardest:
            submissions.sort(key=lambda sub: (sub.problem.rating or 0, sub.creationTimeSeconds), reverse=True)
        else:
            submissions.sort(key=lambda sub: sub.creationTimeSeconds, reverse=True)

        def make_line(sub):
            data = (f'[{sub.problem.name}]({sub.problem.url})',
                    f'[{sub.problem.rating if sub.problem.rating else "?"}]',
                    f'({cf_common.days_ago(sub.creationTimeSeconds)})')
            return '\N{EN SPACE}'.join(data)

        def make_page(chunk):
            title = '{} solved problems by `{}`'.format('Hardest' if hardest else 'Recently',
                                                        '`, `'.join(handles))
            hist_str = '\n'.join(make_line(sub) for sub in chunk)
            embed = discord_common.cf_color_embed(description=hist_str)
            return title, embed

        pages = [make_page(chunk) for chunk in paginator.chunkify(submissions[:100], 10)]
        paginator.paginate(self.bot, ctx.channel, pages, wait_time=5 * 60, set_pagenum_footers=True)

    @commands.command(brief='Create a mashup', usage='[handles] [+tags]')
    async def mashup(self, ctx, *args):
        """Create a mashup contest using problems within +-100 of average rating of handles provided.
        Add tags with "+" before them.
        """
        handles = [arg for arg in args if arg[0] != '+']
        tags = [arg[1:] for arg in args if arg[0] == '+' and len(arg) > 1]

        handles = handles or ('!' + str(ctx.author),)
        handles = await cf_common.resolve_handles(ctx, self.converter, handles)
        resp = [await cf.user.status(handle=handle) for handle in handles]
        submissions = [sub for user in resp for sub in user]
        solved = {sub.problem.name for sub in submissions}
        info = await cf.user.info(handles=handles)
        rating = int(round(sum(user.effective_rating for user in info) / len(handles), -2))
        problems = [prob for prob in cf_common.cache2.problem_cache.problems
                    if abs(prob.rating - rating) <= 100 and prob.name not in solved
                    and not any(cf_common.is_contest_writer(prob.contestId, handle) for handle in handles)
                    and not cf_common.is_nonstandard_problem(prob)]
        if tags:
            problems = [prob for prob in problems if prob.tag_matches(tags)]

        if len(problems) < 4:
            raise CodeforcesCogError('Problems not found within the search parameters')

        problems.sort(key=lambda problem: cf_common.cache2.contest_cache.get_contest(
            problem.contestId).startTimeSeconds)

        choices = []
        for i in range(4):
            k = max(random.randrange(len(problems) - i) for _ in range(2))
            for c in choices:
                if k >= c:
                    k += 1
            choices.append(k)
            choices.sort()

        problems = reversed([problems[k] for k in choices])
        msg = '\n'.join(f'{"ABCD"[i]}: [{p.name}]({p.url}) [{p.rating}]' for i, p in enumerate(problems))
        str_handles = '`, `'.join(handles)
        embed = discord_common.cf_color_embed(description=msg)
        await ctx.send(f'Mashup contest for `{str_handles}`', embed=embed)


    @commands.command(brief='Recommend a contest', usage='[handles...] [+pattern...]')
    async def vc(self, ctx, *args: str):
        """Recommends a contest based on Codeforces rating of the handle provided.
        e.g ;vc mblazev c1729 +global +hello +goodbye +avito"""
        markers = [x for x in args if x[0] == '+']
        handles = [x for x in args if x[0] != '+'] or ('!' + str(ctx.author),)
        handles = await cf_common.resolve_handles(ctx, self.converter, handles, maxcnt=25)
        info = await cf.user.info(handles=handles)
        contests = cf_common.cache2.contest_cache.get_contests_in_phase('FINISHED')

        if not markers:
            divr = sum(user.effective_rating for user in info) / len(handles)
            div1_indicators = ['div1', 'global', 'avito', 'goodbye', 'hello']
            markers = ['div3'] if divr < 1600 else ['div2'] if divr < 2100 else div1_indicators

        recommendations = {contest.id for contest in contests if
                           contest.matches(markers) and
                           not cf_common.is_nonstandard_contest(contest) and
                           not any(cf_common.is_contest_writer(contest.id, handle)
                                       for handle in handles)}

        # Discard contests in which user has non-CE submissions.
        visited_contests = await cf_common.get_visited_contests(handles)
        recommendations -= visited_contests

        if not recommendations:
            raise CodeforcesCogError('Unable to recommend a contest')

        recommendations = list(recommendations)
        random.shuffle(recommendations)
        contests = [cf_common.cache2.contest_cache.get_contest(contest_id) for contest_id in recommendations[:25]]

        def make_line(c):
            return f'[{c.name}]({c.url}) {cf_common.pretty_time_format(c.durationSeconds)}'

        def make_page(chunk):
            str_handles = '`, `'.join(handles)
            message = f'Recommended contest(s) for `{str_handles}`'
            vc_str = '\n'.join(make_line(contest) for contest in chunk)
            embed = discord_common.cf_color_embed(description=vc_str)
            return message, embed

        pages = [make_page(chunk) for chunk in paginator.chunkify(contests, 5)]
        paginator.paginate(self.bot, ctx.channel, pages, wait_time=5 * 60, set_pagenum_footers=True)

    # @commands.command(brief="Display unsolved rounds closest to completion", usage='[handle] [keywords]')
    # async def fullsolve(self, ctx, handle:str, *args: str):
    #     """Displays a list of contests, sorted by number of unsolved problems.
    #     Contest names matching any of the provided tags will be considered. e.g ;fullsolve +edu"""

    #     tags = [x for x in args if x[0] == '+']

    #     problem_to_contests = cf_common.cache2.problemset_cache.problem_to_contests
    #     contests = [contest for contest in cf_common.cache2.contest_cache.get_contests_in_phase('FINISHED')
    #                 if (not tags or contest.matches(tags)) and not cf_common.is_nonstandard_contest(contest)]

    #     # subs_by_contest_id contains contest_id mapped to [list of problem.name]
    #     subs_by_contest_id = defaultdict(set)
    #     for sub in await cf.user.status(handle=handle):
    #         if sub.verdict == 'OK':
    #             try:
    #                 contest = cf_common.cache2.contest_cache.get_contest(sub.problem.contestId)
    #                 problem_id = (sub.problem.name, contest.startTimeSeconds)
    #                 for contestId in problem_to_contests[problem_id]:
    #                     subs_by_contest_id[contestId].add(sub.problem.name)
    #             except cache_system2.ContestNotFound:
    #                 pass

    #     contest_unsolved_pairs = []
    #     for contest in contests:
    #         num_solved = len(subs_by_contest_id[contest.id])
    #         try:
    #             num_problems = len(cf_common.cache2.problemset_cache.get_problemset(contest.id))
    #             if 0 < num_solved < num_problems:
    #                 contest_unsolved_pairs.append((contest, num_solved, num_problems))
    #         except cache_system2.ProblemsetNotCached:
    #             # In case of recent contents or cetain bugged contests
    #             pass

    #     contest_unsolved_pairs.sort(key=lambda p: (p[2] - p[1], -p[0].startTimeSeconds))

    #     if not contest_unsolved_pairs:
    #         raise CodeforcesCogError(f'`{handle}` has no contests to fullsolve :confetti_ball:')

    #     def make_line(entry):
    #         contest, solved, total = entry
    #         return f'[{contest.name}]({contest.url})\N{EN SPACE}[{solved}/{total}]'

    #     def make_page(chunk):
    #         message = f'Fullsolve list for `{handle}`'
    #         full_solve_list = '\n'.join(make_line(entry) for entry in chunk)
    #         embed = discord_common.cf_color_embed(description=full_solve_list)
    #         return message, embed

    #     pages = [make_page(chunk) for chunk in paginator.chunkify(contest_unsolved_pairs, 10)]
    #     paginator.paginate(self.bot, ctx.channel, pages, wait_time=5 * 60, set_pagenum_footers=True)

    @staticmethod
    def getEloWinProbability(ra: float, rb: float) -> float:
        return 1.0 / (1 + 10**((rb - ra) / 400.0))

    @staticmethod
    def composeRatings(left: float, right: float, ratings: List[float]) -> int:
        for tt in range(20):
            r = (left + right) / 2.0

            rWinsProbability = 1.0
            for rating, count in ratings:
                rWinsProbability *= Codeforces.getEloWinProbability(r, rating)**count

            if rWinsProbability < 0.5:
                left = r
            else:
                right = r
        return round((left + right) / 2)

    @commands.command(brief='Calculate team rating', usage='[handles] [+peak]')
    async def teamrate(self, ctx, *args: str):
        """Provides the combined rating of the entire team.
        If +server is provided as the only handle, will display the rating of the entire server.
        Supports multipliers. e.g: ;teamrate gamegame*1000"""

        (is_entire_server, peak), handles = cf_common.filter_flags(args, ['+server', '+peak'])
        handles = handles or ('!' + str(ctx.author),)

        def rating(user):
            return user.maxRating if peak else user.rating

        if is_entire_server:
            res = cf_common.user_db.get_cf_users_for_guild(ctx.guild.id)
            ratings = [(rating(user), 1) for user_id, user in res if user.rating is not None]
            user_str = '+server'
        else:
            def normalize(x):
                return [i.lower() for i in x]
            handle_counts = {}
            parsed_handles = []
            for i in handles:
                parse_str = normalize(i.split('*'))
                if len(parse_str) > 1:
                    try:
                        handle_counts[parse_str[0]] = int(parse_str[1])
                    except ValueError:
                        raise CodeforcesCogError("Can't multiply by non-integer")
                else:
                    handle_counts[parse_str[0]] = 1
                parsed_handles.append(parse_str[0])

            cf_handles = await cf_common.resolve_handles(ctx, self.converter, parsed_handles, mincnt=1, maxcnt=1000)
            cf_handles = normalize(cf_handles)
            cf_to_original = {a: b for a, b in zip(cf_handles, parsed_handles)}
            original_to_cf = {a: b for a, b in zip(parsed_handles, cf_handles)}
            users = await cf.user.info(handles=cf_handles)
            user_strs = []
            for a, b in handle_counts.items():
                if b > 1:
                    user_strs.append(f'{original_to_cf[a]}*{b}')
                elif b == 1:
                    user_strs.append(original_to_cf[a])
                elif b <= 0:
                    raise CodeforcesCogError('How can you have nonpositive members in team?')

            user_str = ', '.join(user_strs)
            ratings = [(rating(user), handle_counts[cf_to_original[user.handle.lower()]])
                       for user in users if user.rating]

        if len(ratings) == 0:
            raise CodeforcesCogError("No CF usernames with ratings passed in.")

        left = -100.0
        right = 10000.0
        teamRating = Codeforces.composeRatings(left, right, ratings)
        embed = discord.Embed(title=user_str, description=teamRating, color=cf.rating2rank(teamRating).color_embed)
        await ctx.send(embed = embed)

    @discord_common.send_error_if(CodeforcesCogError, cf_common.ResolveHandleError,
                                  cf_common.FilterError)
    async def cog_command_error(self, ctx, error):
        pass


def setup(bot):
    bot.add_cog(Codeforces(bot))
