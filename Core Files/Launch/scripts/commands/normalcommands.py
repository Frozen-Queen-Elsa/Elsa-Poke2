"""
Normal Commands Module
"""


# pylint: disable=unused-argument, too-many-locals

import asyncio
import os
import random
import re
from itertools import groupby
from math import ceil
from typing import List, Optional

import aiohttp
import discord
from discord import (
    Message, Member,
    TextChannel, CategoryChannel
)

from ..helpers.checks import (
    poketwo_embed_cmd,
    user_check
)
from ..helpers.paginator import Paginator
from ..helpers.utils import (
    get_embed, get_message,
    get_modules, wait_for,
    send_embed, edit_embed
)
from .basecommand import (
    Commands, check_db, get_chan,
    paginated, soft_paginated
)


class NormalCommands(Commands):
    '''
    Commands which don't have to interact with the pokebots.
    They might still require DB access to get the caught_pokemon tables.
    Examples: Spam, Total, Duplicates, Legendaries, Echo.
    '''

    def __generate_help_embed(self, cmd: str, keep_footer: bool = False):
        got_doc = False
        meta = {}
        if cmd.__doc__:
            if getattr(cmd, "disabled", False):
                cmd_name = cmd.__name__.replace('cmd_', '').title()
                emb = get_embed(
                    f"**{cmd_name}** is under maintainence.\n"
                    "Details unavailable, so wait for updates.",
                    embed_type="warning",
                    title="Command under Maintainence."
                )
                return emb
            got_doc = True
            doc_str = cmd.__doc__.replace(
                "{command_prefix}",
                self.ctx.prefix
            )
            patt = r"\$(?P<Syntax>[^\$]+)\$\s+" + \
                r"\@(?P<Description>[^\@]+)" + \
                r"\@(?:\s+\~(?P<Example>[^\~]+)\~)?"
            meta = re.search(patt, doc_str).groupdict()
            emb = get_embed(
                title=cmd.__name__.replace("cmd_", "").title(),
                content='\u200B',
                color=11068923
            )
        else:
            emb = get_embed(
                "No help message exists for this command.",
                embed_type="warning",
                title="No documentation found."
            )
        for key, val in meta.items():
            if val:
                val = val.replace("  ", " ")
                val = '\n'.join(
                    m.lstrip()
                    for m in val.split('\n')
                )
                emb.add_field(name=f"**{key}**", value=val, inline=False)
        if all([
            got_doc,
            "alias" in dir(cmd)
        ]):
            alt_names = getattr(cmd, "alias")[:]
            if cmd.__name__.replace("cmd_", "") not in alt_names:
                alt_names.append(cmd.__name__.replace("cmd_", ""))
            alias_str = ', '.join(sorted(alt_names, key=len))
            emb.add_field(
                name="**Alias**",
                value=f"```\n{alias_str}\n```"
            )
        if keep_footer and got_doc:
            emb.set_footer(
                text="This command helped? You can help me too "
                "by donating at https://www.paypal.me/hyperclaw79.",
                icon_url="https://emojipedia-us.s3.dualstack.us-west-1."
                "amazonaws.com/thumbs/160/facebook/105/money-bag_1f4b0.png"
            )
        return emb

    async def __get_poketwo(self, message: Message):
        try:
            poketwo = await message.guild.query_members(
                user_ids=[int(self.ctx.configs["clone_id"])]
            )
            poketwo_role = [
                role
                for role in poketwo[0].roles
                if role.name.lower() != "@everyone"
            ][0]
            return poketwo, poketwo_role
        except (TypeError, IndexError):
            self.logger.pprint(
                "Did not find the Poketwo (or expected clone) in here. "
                "Please invite it before executing this command."
                "\nHere's the invite:"
                "\nhttps://discordapp.com/oauth2/authorize?client_id="
                f"{self.ctx.configs['clone_id']}&scope=bot&permissions=387072",
                color="red"
            )
            return None, None

    async def __get_text_catog(self, message: Message):
        text_catog = discord.utils.find(
            lambda x: x.name.upper() == "Pokeball Channels",
            message.guild.categories
        )
        if not text_catog:
            text_catog = discord.utils.find(
                lambda x: x.name.upper() == "TEXT CHANNELS",
                message.guild.categories
            )
        if not text_catog:
            try:
                text_catog = await message.guild.create_category(
                    "Pokeball Channels"
                )
                await text_catog.edit(position=0)
            except (discord.Forbidden, discord.HTTPException):
                return
        return text_catog

    async def __create_channel(
        self, message: Message,
        text_catog: CategoryChannel,
        name: str, disp: Message
    ):
        num_reply = await wait_for(
            message.channel, self.ctx,
            init_msg=disp,
            check=lambda msg: user_check(msg, message),
            timeout="infinite"
        )
        try:
            num = min(int(num_reply.content), 3)
        except ValueError:
            num = 1
        for i in range(num):
            await message.guild.create_text_channel(
                name=f"{name}-{i+1}",
                category=text_catog
            )
        await num_reply.delete()

    async def cmd_setup_server(self, message: Message, **kwargs):
        # pylint: disable=missing-function-docstring
        poketwo, poketwo_role = await self.__get_poketwo(message)
        if not poketwo:
            return
        pref_msg = await message.channel.send(f"{poketwo[0].mention} ping")
        poke_reply = await wait_for(
            message.channel, self.ctx, init_msg=pref_msg,
            check=lambda msg: poketwo_embed_cmd(
                msg, self.ctx,
                message, title_contains="Terms"
            )
        )
        if poke_reply:
            buttons = poke_reply.buttons
            if "Accept" in buttons:
                await buttons['Accept'].click()
        perms = {
            "create_instant_invite": False,
            "manage_webhooks": False
        }
        try:
            secret_channel, disp = await self.__setup_channels(
                message, poketwo_role, perms
            )
            await disp.delete()
            self.logger.pprint(
                f"Finished setting up the server >{message.guild} succesfully.",
                color="green"
            )
            emb = get_embed(
                title="Successfully finished setting up this server!",
                content="From now, use the commands only in the "
                f"{secret_channel.mention} channel.",
                color=16766720,
                url="https://www.paypal.com/paypalme2/hyperclaw79/5"
            )
            emb.set_footer(
                text="Consider dropping a star on my github repo, thanks.\n"
                "https://github.com/Hyperclaw79/PokeBall-SelfBot",
                icon_url="https://raw.githubusercontent.com/Hyperclaw79/"
                "PokeBall-SelfBot/master/assets/pikastar.png"
            )
            await send_embed(
                secret_channel,
                content=message.author.mention,
                embed=emb
            )
        except discord.Forbidden:
            self.logger.pprint(
                "Bot account needs admin permissions "
                f"on the server {message.guild}.",
                color="red"
            )
            return

    async def __setup_channels(self, message, poketwo_role, perms):
        text_catog = await self.__get_text_catog(message)
        if not text_catog:
            raise discord.Forbidden
        await text_catog.set_permissions(poketwo_role, **perms)
        secret_channel = await message.guild.create_text_channel(
                name="secret",
                category=text_catog
            )
        await secret_channel.set_permissions(
                poketwo_role,
                read_messages=False
            )
        channel_types = [
                "spam",
                "duel",
                "trade",
                "market"
            ]
        for i, name in enumerate(channel_types):
            embed = get_embed(
                    f"Enter the number of {name} channels. (Max 3)",
                    title=f"**{name.title()}**"
                )
            if i == 0:
                disp = await send_embed(message.channel, embed=embed)
            else:
                await edit_embed(disp, embed=embed)
            await self.__create_channel(message, text_catog, name, disp)
        return secret_channel, disp

    @get_chan
    async def cmd_spam(self, message: Message, **kwargs):
        """Spams with content fetched from free APIs.
        $```scss
            {command_prefix}spam
        ```$

        @🌟 The infamous autospammer!
        This command spams in the channel where the command is triggered.
        One of the best discord spammers out there.
        This cannot be flagged by the built-in spam detectors of the other bots.
        Use this private channels, away from other humans you don't trust.@

        ~To start spamming in the channel:
            ```
            {command_prefix}toggle spam on
            {command_prefix}spam
            ```
        To stop all the spamming activity:
            ```
            {command_prefix}toggle spam off
            ```~
        """
        async def spam(
            self, message: Message,
            chan: TextChannel, extreme: bool = False,
            boost: bool = False, **kwargs
        ):
            while self.ctx.allow_spam:
                while self.ctx.catching:
                    await asyncio.sleep(self.ctx.configs["delay"])
                content = await get_message(self.ctx.sess)
                if extreme:
                    delay = 0
                elif boost:
                    delay = random.uniform(0.1, 0.5)
                else:
                    delay = 0.5 + random.uniform(0, 0.5)
                try:
                    async with chan.typing():
                        await chan.send(content)
                    await asyncio.sleep(delay)
                except (
                    discord.errors.DiscordServerError,
                    aiohttp.client_exceptions.ClientOSError,
                    discord.errors.HTTPException
                ):
                    await asyncio.sleep(0.1)
                    continue
                await asyncio.sleep(delay)
        boost = False
        extreme = False
        chan = kwargs["chan"]
        if not self.ctx.allow_spam:
            self.logger.pprint(
                "Spamming is not toggled on.",
                timestamp=True,
                color="yellow"
            )
            return
        self.logger.pprint(
            f"Spamming in the #{chan.name} on >{message.guild.name}.",
            timestamp=True,
            color="blue"
        )
        if kwargs.get("extreme", None):
            self.logger.pprint(
                "Spamming in EXTREME mode!",
                timestamp=True,
                color="blue"
            )
            extreme = True
        elif kwargs.get("boost", None):
            self.logger.pprint(
                "Spamming in Boost mode!",
                timestamp=True,
                color="blue"
            )
            boost = True
        self.ctx.task_tracker.register("spam", spam)
        self.ctx.loop.create_task(
            spam(self, message, chan, extreme, boost)
        )

    @get_chan
    async def cmd_echo(
        self, message: Message,
        args: Optional[List[str]] = None,
        mentions: Optional[List[Member]] = None,
        **kwargs
    ):
        """Echoes the input message with support for mentioning users.
        $```scss
        {command_prefix}echo [@mention] message
        ```$

        @Basically echo whatever you say. Useful for testing connectivity.
        Also, Useful when operating Discord from different account.@

        ~To echo "test":
            ```
            {command_prefix}echo test
            ```
        To mention the user ABC#1234 and say something:
            ```
            {command_prefix}echo @ABC#1234 sup?
            ```~
        """
        chan = kwargs["chan"]
        if not args:
            return
        mention_str = ' '.join(
            mention.mention
            for mention in set(mentions)
        )
        await chan.send(
            f"{' '.join(args)} {mention_str}"
        )

    @soft_paginated
    async def cmd_help(
        self, message: Message,
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """What did you expect? This is just the Help command.
        $```scss
        {command_prefix}help [command]
        ```$

        @Prints a help message.
        If a command is specified, it prints a help message for that command.
        Otherwise, it lists the available commands.@

        ~To view help for a specific command, say, `total`:
            ```
            {command_prefix}help total
            ```
        To view help for all the commands:
            ```
            {command_prefix}help
            ```~
        """
        modules = get_modules(self.ctx)
        commands = unfiltered_commands = list(
            {
                getattr(module, attr)
                for module in modules
                for attr in dir(module)
                if all(
                    [
                        module.enabled,
                        attr.startswith("cmd_"),
                        attr.__doc__ is not None
                    ]
                )
            }
        )
        modules = sorted(
            modules,
            key=lambda x: "Custom" in x.__class__.__name__,
            reverse=True
        )
        if args:
            commands = []
            for cmd in unfiltered_commands:
                if any([
                    cmd.__name__ == f"cmd_{args[0].lower()}",
                    args[0].lower() in getattr(cmd, "alias", [])
                ]) and cmd.__name__ not in (
                    cm.__name__ for cm in commands
                ):
                    commands.append(cmd)
            if not commands:
                await send_embed(
                    message.channel,
                    embed=get_embed(
                        f"There's no command called **{args[0].title()}**\n"
                        "Or you don't have access to it.",
                        embed_type="error"
                    )
                )
                return
        embeds = []
        for i, cmd in enumerate(commands):
            if len(args) > 0:
                emb = self.__generate_help_embed(cmd, keep_footer=True)
            else:
                emb = self.__generate_help_embed(cmd)
                emb.set_footer(text=f"{i+1}/{len(commands)}")
            embeds.append(emb)
        base = await send_embed(
            message.channel,
            content='**PokeBall SelfBot Commands List:**\n',
            embed=embeds[0]
        )
        if len(embeds) > 1:
            pager = Paginator(message, base, embeds, self.ctx)
            await pager.run(content='**PokeBall SelfBot Commands List:**\n')

    async def cmd_donate(
        self, message: Message,
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Feel free to buy me a cup of coffee, thanks!
        $```scss
        {command_prefix}donate [amount in USD]
        ```$

        @Opens a donation window on your browser where you can support me.@
        """
        amt = (
            int(args[0]) if args and len(args) > 0 and args[0].isdigit()
            else 10
        )
        emb = get_embed(
            title="**Thank you very much for you generousness.**",
            color=16766720,
            url=f"https://www.paypal.com/paypalme2/hyperclaw79/{amt}"
        )
        emb.set_image(
            url="https://raw.githubusercontent.com/Hyperclaw79"
            "/PokeBall-SelfBot/master/assets/pikadonor.png"
        )
        await send_embed(message.channel, embed=emb)
        _ = os.system(f'start https://www.paypal.com/paypalme2/hyperclaw79/{amt}')

    async def cmd_commands(self, message: Message, **kwargs):
        """List all usable commands for the user.
        $```scss
        {command_prefix}commands [--module name]
        ```$

        @Lists out all the commands you could use.
        You can provide a module name to see its commands.@

        ~To check the commands list:
            ```
            {command_prefix}commands
            ```
        To check only profile commands:
            ```
            {command_prefix}commands --module profile
            ```~
        """
        modules = [
            getattr(self.ctx, comtype)
            for comtype in dir(self.ctx)
            if all([
                comtype.endswith('commands'),
                comtype != "load_commands"
            ])
        ]
        modules = sorted(
            modules,
            key=lambda x: x.__class__.__name__,
            reverse=True
        )
        command_dict = {
            module.__class__.__name__.replace(
                "Commands", " Commands"
            ): '\n'.join(
                sorted(
                    [
                        cmd.replace("cmd_", self.ctx.prefix)
                        for cmd in dir(module)
                        if all([
                            cmd.startswith("cmd_"),
                            "disabled" not in dir(getattr(module, cmd)),
                            getattr(module, cmd).__doc__
                        ])
                    ],
                    key=len
                )
            )
            for module in modules
        }
        embed = get_embed(
            f"Use `{self.ctx.prefix}help [command name]` for details",
            title="Pokeball Selfbot Commands List"
        )
        for key, val in command_dict.items():
            if val:
                embed.add_field(name=key, value=f"**```\n{val}\n```**")
        embed.set_footer(
            text="This command helped? You can help me too by "
            "donating at https://www.paypal.me/hyperclaw79.",
            icon_url="https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/"
            "thumbs/160/facebook/105/money-bag_1f4b0.png"
        )
        await send_embed(message.channel, embed=embed)

    @paginated
    @check_db
    async def cmd_legendary(self, message: Message, **kwargs):
        """List the captured legendaries.
        $```scss
        {command_prefix}legendary
        ```$

        @Posts a paginated embed which shows all your caught legendaries.@
        """
        embeds = []
        names = [
            poke
            for poketype in ["legendary", "mythical", "ultrabeast"]
            for poke in self.ctx.pokeranks[poketype]
        ]
        for i in range(0, len(names), 5):
            embed = get_embed(
                title="Legendaries",
                content="\u200B",
                color=15728640
            )
            for legend in names[i:i+5]:
                ids = self.database.get_ids(name=legend)
                if len(ids) > 0:
                    val = '\n'.join(
                        ','.join(str(_id) for _id in ids[i:i + 5])
                        for i in range(0, len(ids), 5)
                    )

                    if len(val) >= 2000:
                        emb = get_embed(
                            "Woah dude, too many legendaries!\n"
                            "Consider trading them with "
                            f"`{self.ctx.prefix}trade` to {self.ctx.owner}.",
                            embed_type="error",
                            title="Too Many Duplicates"
                        )
                        await send_embed(message.channel, embed=emb)
                        return
                else:
                    val = "None Caught Yet."
                embed.add_field(name=legend, value=val, inline=False)
            embeds.append(embed)
        base = await send_embed(message.channel, content=None, embed=embeds[0])
        pager = Paginator(message, base, embeds, self.ctx)
        await pager.run()

    @paginated
    @check_db
    async def cmd_duplicates(
        self, message: Message,
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Get pokemons with duplicates more than specified limit.
        $```scss
        {command_prefix}duplicates (limit)
        ```$

        @List out all the duplicates you've caught so far.
        A limit/treshold can be gives as an arg.
        By default, the treshold is `2`.@

        ~To get a list of all pokemons with atleast 3 duplicates:
            ```
            {command_prefix}duplicates 3
            ```
        To get a complete list of all duplicate pokemons you have:
            ```
            {command_prefix}duplicates
            ```~
        """
        limit = int(args[0]) if args else 2
        dups = self.database.fetch_query(dup_count=limit, order_by='name')
        if len(dups) == 0:
            await message.channel.send(
                "There is no pokemon with so many duplicates.\n"
                "Try a smaller number."
            )
            return
        dups = {
            name: list(matches)
            for name, matches in groupby(dups, key=lambda x: x['name'])
        }
        embeds = []
        for i in range(0, len(dups), 5):
            embed = get_embed(
                title="Duplicates",
                content="\u200B",
                color=15728640
            )
            for name, matches in list(dups.items())[i:i+5]:
                data = [
                    f"**ID**: {match['pokeid']}\t"
                    f"**LEVEL**: {match['level']}\t"
                    f"**IV**: {match['iv']}%"
                    for match in matches
                ]
                data.append('-' * 55)
                embed.add_field(
                    name=f"**{name}**",
                    value='\n'.join(data),
                    inline=False
                )
            embed.set_footer(text=f"{(i//5)+1}/{ceil(len(dups)/5)}")
            embeds.append(embed)
        try:
            base = await send_embed(
                message.channel,
                content=None,
                embed=embeds[0]
            )
            pager = Paginator(message, base, embeds, self.ctx)
            await pager.run()
        except discord.errors.HTTPException:
            emb = get_embed(
                "Looks like you have way too many duplicates.\n"
                "Consider purging them with "
                f"`{self.ctx.prefix}mass_sell dupes` first.",
                embed_type="error",
                title="Too Many Duplicates"
            )
            await send_embed(message.channel, embed=emb)

    @check_db
    async def cmd_total(self, message: Message, **kwargs):
        """Total logged pokemons in the DB.
        $```scss
        {command_prefix}total
        ```$

        @View the total number of pokemons logged in the database.
        Automatically called upon using `{command_prefix}pokelog`.@
        """
        emb = get_embed(
            content=f"{self.database.get_total()}",
            embed_type="info",
            title="Total Number of Pokemons"
        )
        await send_embed(message.channel, embed=emb)

    async def cmd_verified(self, message: Message, **kwargs):
        """Captcha Lock Bypass.
        $```scss
        {command_prefix}verified
        ```$

        @Bypass the 24hr captcha lock after manually verifying captcha.
        Takes effect only when the lock is activated.
        You can also use this command before solving the captcha while locked.@
        """
        if not self.ctx.verified:
            self.logger.pprint(
                "Bypassing Captcha lock now.",
                color="green",
                timestamp=True
            )
            self.ctx.verified = True
