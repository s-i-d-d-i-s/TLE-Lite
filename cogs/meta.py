import os
import subprocess
import sys
import time
import textwrap
import discord
from discord.ext import commands
from util.codeforces_common import pretty_time_format
import TLEconstants 
RESTART = 42


class Meta(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

    @commands.group(brief='Bot control', invoke_without_command=True)
    async def meta(self, ctx):
        """Command the bot or get information about the bot."""
        await ctx.send_help(ctx.command)


    @meta.command(brief='Kill TLE')
    @commands.has_role('Admin')
    @commands.has_role('Developer')
    async def kill(self, ctx):
        """Restarts the bot."""
        if str(ctx.author.id) == TLEconstants.OWNER_ID:
            await ctx.send('Dying...')
            os._exit(0)
        else:
            await ctx.send("Nice try but bruh...You don't own this instance of TLE")

    @meta.command(brief='Is TLE up?')
    async def ping(self, ctx):
        """Replies to a ping."""
        start = time.perf_counter()
        message = await ctx.send(':ping_pong: Pong!')
        end = time.perf_counter()
        duration = (end - start) * 1000
        await message.edit(content=f'REST API latency: {int(duration)}ms\n'
                                   f'Gateway API latency: {int(self.bot.latency * 1000)}ms')

    @meta.command(brief='Prints bot uptime')
    async def uptime(self, ctx):
        """Replies with how long TLE has been up."""
        await ctx.send('TLE has been running for ' +
                       pretty_time_format(time.time() - self.start_time))

    @meta.command(brief="Introduce the Bot")
    async def intro(self,ctx):
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
        await ctx.send(embed=embed)

    @meta.command(brief='Print bot guilds')
    @commands.has_role('Admin')
    @commands.has_role('Developer')
    async def guilds(self, ctx):
        "Replies with info on the bot's guilds"
        msg = [f'Guild ID: {guild.id} | Name: {guild.name} | Owner: {guild.owner.id} | Icon: {guild.icon_url}'
                for guild in self.bot.guilds]
        await ctx.send('```' + '\n'.join(msg) + '```')


def setup(bot):
    bot.add_cog(Meta(bot))
