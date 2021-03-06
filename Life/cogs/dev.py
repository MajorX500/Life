import sys

import asyncpg
import discord
import humanize
import pkg_resources
import setproctitle
from discord.ext import commands

from cogs.utilities import exceptions


class Dev(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

        setproctitle.setproctitle('LifeBot')

    async def cog_check(self, ctx):
        if ctx.author.id in self.bot.owner_ids:
            return True
        raise commands.NotOwner()

    @commands.group(name='dev', hidden=True, invoke_without_command=True)
    async def dev(self, ctx):
        """
        Base command for bot developer commands.

        Displays a message with stats about the bot.
        """

        python_version = f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'
        discordpy_version = pkg_resources.get_distribution('discord.py').version
        platform = sys.platform
        process_name = setproctitle.getproctitle()
        process_id = self.bot.process.pid
        thread_count = self.bot.process.num_threads()

        description = [f'I am running on the python version **{python_version}** on the OS **{platform}** '
                       f'using the discord.py version **{discordpy_version}**. '
                       f'The process is running as **{process_name}** on PID **{process_id}** and is using '
                       f'**{thread_count}** threads.']

        if isinstance(self.bot, commands.AutoShardedBot):
            description.append(f'The bot is automatically sharded with **{self.bot.shard_count}** shard(s) and can '
                               f'see **{len(self.bot.guilds)}** guilds and **{len(self.bot.users)}** users.')
        else:
            description.append(f'The bot is not sharded and can see **{len(self.bot.guilds)}** guilds and '
                               f'**{len(self.bot.users)}** users.')

        with self.bot.process.oneshot():

            memory_info = self.bot.process.memory_full_info()
            physical_memory = humanize.naturalsize(memory_info.rss)
            virtual_memory = humanize.naturalsize(memory_info.vms)
            unique_memory = humanize.naturalsize(memory_info.uss)
            cpu_usage = self.bot.process.cpu_percent(interval=None)

            description.append(f'The process is using **{physical_memory}** of physical memory, **{virtual_memory}** '
                               f'of virtual memory and **{unique_memory}** of memory that is unique to the process. '
                               f'It is also using **{cpu_usage}%** of CPU.')

        embed = discord.Embed(title=f'{self.bot.user.name} bot information page.', colour=0xF5F5F5)
        embed.description = '\n\n'.join(description)

        return await ctx.send(embed=embed)

    @dev.command(name='cleanup', aliases=['clean'], hidden=True)
    async def dev_cleanup(self, ctx, limit: int = 50):
        """
        Cleans up the bots messages.

        `limit`: The amount of messages to check back through. Defaults to 50.
        """

        prefix = self.bot.config.PREFIX

        if ctx.channel.permissions_for(ctx.me).manage_messages:
            messages = await ctx.channel.purge(check=lambda m: m.author == ctx.me or m.content.startswith(prefix),
                                               bulk=True, limit=limit)
        else:
            messages = await ctx.channel.purge(check=lambda m: m.author == ctx.me, bulk=False, limit=limit)

        return await ctx.send(f'I found and deleted `{len(messages)}` of my '
                              f'message(s) out of the last `{limit}` message(s).', delete_after=3)

    @dev.command(name='guilds', hidden=True)
    async def dev_guilds(self, ctx, guilds: int = 20):
        """
        A list of guilds with the ratio of bots to members.

        `guilds`: The amount of guilds to show per page.
        """

        entries = []

        for guild in sorted(self.bot.guilds, reverse=True,
                            key=lambda g: (sum(1 for m in g.members if m.bot) / len(g.members)) * 100):

            total = len(guild.members)
            members = sum(1 for m in guild.members if not m.bot)
            bots = sum(1 for m in guild.members if m.bot)
            percent_bots = f'{round((bots / total) * 100, 2)}%'

            entries.append(f'{guild.id:<18} |{total:<9}|{members:<9}|{bots:<9}|{percent_bots:9}|{guild.name}')

        header = 'Guild id           |Total    |Members  |Bots     |Percent  |Name\n'
        return await ctx.paginate_codeblock(entries=entries, entries_per_page=guilds, header=header)

    @dev.group(name='blacklist', aliases=['bl'], hidden=True, invoke_without_command=True)
    async def dev_blacklist(self, ctx):
        """
        Base command for blacklisting.
        """

        return await ctx.send(f'Please choose a valid subcommand. Use `{self.bot.config.PREFIX}help dev blacklist` '
                              f'for more information.')

    @dev_blacklist.command(name='reload', hidden=True)
    async def dev_blacklist_reload(self, ctx):
        """
        Reload the bot's blacklist.
        """

        blacklisted_users = await self.bot.db.fetch('SELECT * FROM blacklist WHERE type = $1', 'user')
        for user in blacklisted_users:
            self.bot.user_blacklist[user['id']] = user['reason']
        print(f'\n[BLACKLIST] Reloaded user blacklist. [{len(blacklisted_users)} users]')

        blacklisted_guilds = await self.bot.db.fetch('SELECT * FROM blacklist WHERE type = $1', 'guild')
        for guild in blacklisted_guilds:
            self.bot.guild_blacklist[guild['id']] = guild['reason']
        print(f'[BLACKLIST] Reloaded guild blacklist. [{len(blacklisted_guilds)} guilds]')

        return await ctx.send('Reloaded the blacklists.')

    @dev_blacklist.group(name='user', hidden=True, invoke_without_command=True)
    async def dev_blacklist_user(self, ctx):
        """
        Display a list of all blacklisted users.
        """

        blacklisted = []
        blacklist = await self.bot.db.fetch('SELECT * FROM blacklist WHERE type = $1', 'user')

        if not blacklist:
            return await ctx.send('No blacklisted users.')

        for entry in blacklist:
            try:
                user = await self.bot.fetch_user(entry['id'])
            except discord.NotFound:
                blacklisted.append(f'{entry["id"]:<18} | {"Not found":<32} | {entry["reason"]}')
            else:
                blacklisted.append(f'{user.id:<18} |{user.name:<32} |{entry["reason"]}')

        header = 'User id            |Name                             |Reason\n'
        return await ctx.paginate_codeblock(entries=blacklisted, entries_per_page=10, header=header)

    @dev_blacklist_user.command(name='add', hidden=True)
    async def dev_blacklist_user_add(self, ctx, user_id: int, *, reason: str = None):
        """
        Add a user to the blacklist.

        `user_id`: The users id.
        `reason`: Why the user is blacklisted.
        """

        try:
            user = await self.bot.fetch_user(user_id)
        except discord.NotFound:
            raise exceptions.ArgumentError(f'User with id `{user_id}` was not found.')

        if not reason:
            reason = user.name

        try:
            self.bot.user_blacklist[user.id] = reason
            await self.bot.db.execute('INSERT INTO blacklist VALUES ($1, $2, $3)', user.id, 'user', reason)
            return await ctx.send(f'User: `{user.name} - {user.id}` has been blacklisted with reason `{reason}`')

        except asyncpg.UniqueViolationError:
            raise exceptions.ArgumentError(f'User with id `{user.id}` is already blacklisted.')

    @dev_blacklist_user.command(name='remove', hidden=True)
    async def dev_blacklist_user_remove(self, ctx, user_id: int):
        """
        Remove a user from the blacklist.

        `user_id`: The users id.
        """

        if user_id not in self.bot.user_blacklist:
            raise exceptions.ArgumentError(f'User with id `{user_id}` is not blacklisted.')

        del self.bot.user_blacklist[user_id]
        await self.bot.db.execute('DELETE FROM blacklist WHERE id = $1', user_id)

        try:
            user = await self.bot.fetch_user(user_id)
        except discord.NotFound:
            message = f'User: `{user_id}` has been un-blacklisted'
        else:
            message = f'User: `{user.name} - {user.id}` has been un-blacklisted'

        return await ctx.send(message)

    @dev_blacklist.group(name='guild', hidden=True, invoke_without_command=True)
    async def dev_blacklist_guild(self, ctx):
        """
        Display a list of all blacklisted guilds.
        """

        blacklisted = []
        blacklist = await self.bot.db.fetch('SELECT * FROM blacklist WHERE type = $1', 'guild')

        if not blacklist:
            return await ctx.send('No blacklisted guilds.')

        for entry in blacklist:
            blacklisted.append(f'{entry["id"]:<18} |{entry["reason"]}')

        header = 'Guild id           |Reason\n'
        return await ctx.paginate_codeblock(entries=blacklisted, entries_per_page=10, header=header)

    @dev_blacklist_guild.command(name='add', hidden=True)
    async def dev_blacklist_guild_add(self, ctx, guild_id: int, *, reason: str = None):
        """
        Add a guild to the blacklist.

        `guild_id`: The guilds id.
        `reason`: Why the guild is blacklisted.
        """

        try:
            guild = await self.bot.fetch_guild(guild_id)
        except discord.Forbidden:
            pass
        else:
            if not reason:
                reason = f'Name: {guild.name}'
            await guild.leave()

        if not reason:
            reason = 'No reason'

        try:
            self.bot.guild_blacklist[guild_id] = reason
            await self.bot.db.execute('INSERT INTO blacklist VALUES ($1, $2, $3)', guild_id, 'guild', reason)
            return await ctx.send(f'Guild: `{guild_id}` has been blacklisted with reason `{reason}`')

        except asyncpg.UniqueViolationError:
            raise exceptions.ArgumentError(f'Guild with id `{guild_id}` is already blacklisted.')

    @dev_blacklist_guild.command(name='remove', hidden=True)
    async def dev_blacklist_guild_remove(self, ctx, guild_id: int):
        """
        Remove a guild from the blacklist.

        `guild_id`: The guilds id.
        """

        if guild_id not in self.bot.guild_blacklist:
            raise exceptions.ArgumentError(f'Guild with id `{guild_id}` is not blacklisted.')

        del self.bot.guild_blacklist[guild_id]
        await self.bot.db.execute('DELETE FROM blacklist WHERE id = $1', guild_id)

        return await ctx.send(f'Guild: `{guild_id}` has been un-blacklisted.')


def setup(bot):
    bot.add_cog(Dev(bot))
