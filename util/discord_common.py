import asyncio
import logging
import functools
import random

import discord
from discord.ext import commands
from discord.utils import find

from util import codeforces_api as cf
from util import db
from util import tasks

logger = logging.getLogger(__name__)

_CF_COLORS = (0xFFCA1F, 0x198BCC, 0xFF2020)
_SUCCESS_GREEN = 0x28A745
_ALERT_AMBER = 0xFFBF00


def embed_neutral(desc, color=discord.Embed.Empty):
    return discord.Embed(description=str(desc), color=color)


def embed_success(desc):
    return discord.Embed(description=str(desc), color=_SUCCESS_GREEN)


def embed_alert(desc):
    return discord.Embed(description=str(desc), color=_ALERT_AMBER)

def random_cf_color():
    return random.choice(_CF_COLORS)

def cf_color_embed(**kwargs):
    return discord.Embed(**kwargs, color=random_cf_color())

def set_same_cf_color(embeds):
    color = random_cf_color()
    for embed in embeds:
        embed.color=color


def attach_image(embed, img_file):
    embed.set_image(url=f'attachment://{img_file.filename}')


def set_author_footer(embed, user):
    embed.set_footer(text=f'Requested by {user}', icon_url=user.avatar_url)


def send_error_if(*error_cls):
    """Decorator for `cog_command_error` methods. Decorated methods send the error in an alert embed
    when the error is an instance of one of the specified errors, otherwise the wrapped function is
    invoked.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(cog, ctx, error):
            if isinstance(error, error_cls):
                await ctx.send(embed=embed_alert(error))
                error.handled = True
            else:
                await func(cog, ctx, error)
        return wrapper
    return decorator


async def bot_error_handler(ctx, exception):
    if getattr(exception, 'handled', False):
        # Errors already handled in cogs should have .handled = True
        return

    if isinstance(exception, db.DatabaseDisabledError):
        await ctx.send(embed=embed_alert('Sorry, the database is not available. Some features are disabled.'))
    elif isinstance(exception, commands.NoPrivateMessage):
        await ctx.send(embed=embed_alert('Commands are disabled in private channels'))
    elif isinstance(exception, commands.DisabledCommand):
        await ctx.send(embed=embed_alert('Sorry, this command is temporarily disabled'))
    elif isinstance(exception, (cf.CodeforcesApiError, commands.UserInputError)):
        await ctx.send(embed=embed_alert(exception))
    else:
        exc_info = type(exception), exception, exception.__traceback__
        logger.exception('Ignoring exception in command {}:'.format(ctx.command), exc_info=exc_info)


def once(func):
    """Decorator that wraps the given async function such that it is executed only once."""
    first = True
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        nonlocal first
        if first:
            first = False
            await func(*args, **kwargs)

    return wrapper


def on_ready_event_once(bot):
    """Decorator that uses bot.event to set the given function as the bot's on_ready event handler,
    but does not execute it more than once.
    """
    @bot.event
    async def on_guild_join(guild):
        general = find(lambda x: x.name == 'general',  guild.text_channels)
        if general and general.permissions_for(guild.me).send_messages:
            desc = "Hi ! I am [TLE-Lite](https://github.com/s-i-d-d-i-s/TLE-Lite), I am a lightweight-ripoff of [TLE](https://github.com/cheran-senthil/TLE)"
            desc += "\n\nI was created because my big brother [TLE](https://github.com/cheran-senthil/TLE) is a pain to setup and host lol :rofl:"
            desc += "\nEven tho im not as cool and orz as him, i'm easy to invite and get most of the job done :wink:"
            desc += "\n\nI'm currently in beta/testing, so i may act wierd sometimes :frowning: "
            desc += "\n\nCheck my Github Repositry to get updates on this project."
            desc += "\n\n[TLE-Lite](https://github.com/s-i-d-d-i-s/TLE-Lite)"
            desc += "\n\n[TLE](https://github.com/cheran-senthil/TLE)"
            desc += "\n\n[Invite Me](https://discord.com/api/oauth2/authorize?client_id=809995275300110357&permissions=8&scope=bot)"
            desc += "\n\nType `;help` to check out my commands"
            desc += "\n\nIf you invite me, make sure that you give me Admin Role\nand you have roles named on all Codeforces Ranks\ne.g `[Newbie,Pupil,Expert...]`"
            desc += "\n\nIf you need help, talk to people working on this project [here](https://discord.gg/7vzwAye2kN)"
            botpic = "https://i.ibb.co/Sx6Jtn2/TLE-Lite-Trans.png"
            embed = discord.Embed(description=desc, color=discord.Colour(0xffff00))
            embed.set_thumbnail(url=botpic)
            await general.send(embed=embed)
    def register_on_ready(func):
        @bot.event
        @once
        async def on_ready():
            await func()

    return register_on_ready


async def presence(bot):
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name='your commands'))
    await asyncio.sleep(60)

    @tasks.task(name='OrzUpdate',
               waiter=tasks.Waiter.fixed_delay(5*60))
    async def presence_task(_):
        while True:
            cnt = 0
            for g in bot.guilds:
                cnt += len(g.members)
                await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"{cnt} members and {len(bot.guilds)} servers !"))
                await asyncio.sleep(10 * 60)

    presence_task.start()

