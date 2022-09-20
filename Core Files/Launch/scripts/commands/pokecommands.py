"""
Poketwo Commands Module
"""

# pylint: disable=too-many-locals, too-many-lines
# pylint: disable=no-member, unused-argument

import asyncio
import random
import re
from math import floor, sqrt
from typing import Dict, List, Optional

from discord import Message, Member, TextChannel

from ..helpers.checks import (
    poketwo_reply_cmd, poketwo_embed_cmd,
    user_check
)
from ..helpers.utils import (
    get_embed, log_formatter, send_embed,
    wait_for
)
from .basecommand import (
    Commands, check_db,
    get_chan, get_prefix
)


class PokeCommands(Commands):
    '''
    Commands which directly interact with the pokebots.
    They require DB access to get the guild_prefixes and the caught_pokemon tables.
    Examples: Trade, Pokelog, Mass_sell, etc.
    '''

    @get_prefix
    @get_chan
    async def cmd_poke_exec(self, message: Message, **kwargs):
        # pylint: disable=missing-function-docstring
        pref = kwargs.pop("pref")
        chan = kwargs.pop("chan")
        args = kwargs.pop("args", None)
        mentions = kwargs.pop("mentions", [])
        kwarg_str = (
            (
                ' ' + ' '.join(
                    f"--{key}" if val is True else f"--{key} {val}"
                    for key, val in kwargs.items()
                )
            )
            if kwargs.items()
            else ''
        )

        if not args:
            return
        command = args.pop(0)
        pokeargs = ' ' + ' '.join(args) if args else ''
        pokementions = (
            (' ' + ' '.join(mention.mention for mention in set(mentions)))
            if mentions
            else ''
        )
        components = [
            pref, command,
            pokementions,
            pokeargs,
            kwarg_str
        ]
        pokecmd = "".join(components)
        msg = await chan.send(pokecmd)
        return msg

    @get_prefix
    @get_chan
    async def cmd_pokelog(
        self, message: Message,
        args: Optional[List[str]] = None,
        fresh: bool = True,
        **kwargs
    ):
        """Log your pokemons to local DB.
        $```scss
        {command_prefix}pokelog [page_number]
        ```$

        @Log all your pokemon with their ids and levels into the local database.
        This can be used for other commands like `{command_prefix}duplicates`,
        `{command_prefix}legendaries` and such.
        The current version of the command is automatic till Poketwo goes offline.
        In such rare cases, you can use the page number to resume logging.@

        ~To log normally:
            ```
            {command_prefix}pokelog
            ```
        If poketwo broke down at the 5th page and got restarted, \
            you'd wanna continue from page 6.
        In that case, use:
            ```
            {command_prefix}pokelog 6
            ```~
        """
        pref = kwargs["pref"]
        chan = kwargs["chan"]
        page = 1
        pokelist = []
        self.ctx.priority_only = True
        if fresh:
            self.database.reset_caught()
            await self.reindex_pk2(message, pref, chan)
        order_msg = await chan.send(f"{pref}order number")
        await wait_for(
            chan, self.ctx, init_msg=order_msg,
            check=lambda msg: poketwo_reply_cmd(
                msg, self.ctx, message, chan=chan,
                contains="Now ordering"
            )
        )
        await asyncio.sleep(random.uniform(1.0, 2.0))
        if args:
            page = int(args[0])
            pk_msg = await chan.send(f"{pref}pokemon {args[0]}")
        else:
            pk_msg = await chan.send(f"{pref}pokemon")
        reply = await wait_for(
            chan, self.ctx, init_msg=pk_msg,
            check=lambda msg: poketwo_embed_cmd(
                msg, self.ctx, message, chan=chan,
                title_contains="Your pokémon"
            )
        )
        pokemons = reply.embeds[0].description.splitlines()
        pokelist = [
            log_formatter(self.ctx, pokemon)
            for pokemon in pokemons
        ]
        if pokelist[0]["iv"] == 0.0:
            self.logger.pprint(
                "Warning! IVs ar disabled. They will be set as 0 in the logs.\n"
                f"Use {pref}!detailed to enable them before logging.",
                timestamp=True,
                color="yellow"
            )
        self.database.insert_bulk(pokelist)
        pokelist = []
        await asyncio.sleep(random.uniform(1.0, 2.0))
        while True:
            delme = await chan.send(f"{pref}n")
            reply = await wait_for(
                chan, self.ctx, event='message', init_msg=delme,
                check=lambda msg: poketwo_embed_cmd(
                    msg, self.ctx, message, chan=chan,
                    title_contains="Your pokémon"
                ),
                timeout=3.0
            )
            if not reply:
                pg_msg = await chan.send(f"{pref}pokemon {page + 1}")
                reply = await wait_for(
                    chan, self.ctx, init_msg=pg_msg,
                    check=lambda msg: poketwo_embed_cmd(
                        msg, self.ctx, message, chan=chan,
                        title_contains="Your pokémon"
                    ),
                    timeout=3.0
                )
            if not reply:
                await chan.send(f"Logged up to page {page}.")
                break
            pokemons = reply.embeds[0].description.splitlines()
            await delme.delete()
            page += 1
            pokelist = [
                log_formatter(self.ctx, pokemon)
                for pokemon in pokemons
            ]
            self.database.insert_bulk(pokelist)
            page_patt = r'entries \d+\–(\d+) out of (\d+)'
            page_match = re.search(page_patt, reply.embeds[0].footer.text)
            if any([
                page_match.group(1) == page_match.group(2),
                len(pokemons) < 20
            ]):
                break
            await asyncio.sleep(random.uniform(1.0, 2.0))
            await message.channel.send(f"Logged up to page {page}.")
        self.logger.pprint(
            f'Logged all the pokemon successfully upto page {page}.\n',
            timestamp=True,
            color="green"
        )
        await self.ctx.normalcommands.cmd_total(
            message=message
        )
        self.ctx.priority_only = False

    @check_db
    @get_prefix
    @get_chan
    async def cmd_trade(
        self, message: Message,
        mentions: List[Member],
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Trade your pokemons to any account.
        $```scss
        {command_prefix}trade @user [IDs/Names/"fav"]
        ```$

        @🌟 Autotrade a list of pokemon to a user and confirm it.
        Can accept either a list of pokemon ids or the keyword "fav" as args.
        Fav means all the mons in your Poketwo Favourite list will be traded.
        Not specifying a list of ids or "fav" will trade all non-priority pokemons.
        However this is not recommended as poketwo might lag.@

        ~To trade the pokemons 1200 and 69 to the user ABC#1234:
            ```
            {command_prefix}trade @ABC#1234 1200 69
            ```
        To trade all the pokemon in your fav list to the user ABC#1234:
            ```
            {command_prefix}trade @ABC#1234 fav
            ```
        To trade all the Groudons and Mewtwos to the user ABC#1234:
            ```
            {command_prefix}trade @ABC#1234 Groudon Mewtwo
            ```
        To trade the pokemons 1200 & 69 and all Charizards to user ABC#1234:
            ```
            {command_prefix}trade @ABC#1234 1200 Charizard 69
            ```~
        """
        user = mentions[0]
        pref = kwargs["pref"]
        chan = kwargs["chan"]
        numlist = []
        if not args:
            numlist = await self.__get_all_ids(message)
        elif "fav" in args:
            numlist = await self.get_pokes(
                message, pref, chan,
                fav=True, ids_only=True
            )
            if numlist:
                id_str = ' '.join(str(pokeid) for pokeid in numlist)
                await chan.send(f"{pref}unfav {id_str}")
        elif "dupes" in args:
            dupes = self.database.get_trash(
                output_cols=["pokeid"],
                iv_threshold=self.ctx.configs["iv_threshold"],
                max_dupes=self.ctx.configs["max_dupes"]
            )
            numlist += [dupe["pokeid"] for dupe in dupes]
        else:
            numlist = await self.__arg2ids(message, args)
        if not numlist:
            self.logger.pprint(
                "No pokemon to trade.",
                timestamp=True,
                color="red"
            )
            return
        numbers = list(set(numlist))
        numbers = sorted(numbers, reverse=True)
        numbatches = [
            numbers[i:i+250]
            for i in range(0, len(numbers), 250)
        ]
        await asyncio.sleep(random.uniform(2.0, 2.5))
        money = kwargs.get("credits")
        if money:
            if kwargs["credits"] in ["max", "all"]:
                money = await self.__get_bal(message, pref, chan)
            if not money:
                self.logger.pprint(
                    'Unable to transfer credits.',
                    timestamp=True,
                    color="yellow"
                )
            numbatches[-1].extend(["pc", money])
        for nums in numbatches:
            traded = await self.__trade(message, user, pref, chan, nums)
            if not traded:
                self.logger.pprint(
                    'Something went wrong, please retry the command.',
                    timestamp=True,
                    color="red"
                )
                return
        if len(numbers) >= 1:
            self.logger.pprint(
                'Successfully traded away all mentioned pokemon.',
                timestamp=True,
                color="green"
            )
            self.database.delete_caught(pokeids=numbers)

    @get_prefix
    @get_chan
    async def cmd_gift(
        self, message: Message,
        mentions: List[Member],
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Gift credits to any account.
        $```scss
        {command_prefix}gift @userX amount
        ```$

        @Trades user X specified amount of pokecredits.@

        ~To give your main account named ABC#1234, 1000c:
            ```
            {command_prefix}gift @ABC#1234 1000
            ```~
        """
        user = mentions[0]
        pref = kwargs["pref"]
        chan = kwargs["chan"]
        if not args:
            self.logger.pprint(
                "You have not entered how much you want to transfer.",
                timestamp=True,
                color="red"
            )
            return
        if args[0] in ["max", "all"]:
            money = await self.__get_bal(message, pref, chan)
        else:
            money = args[0]
        if not money:
            self.logger.pprint(
                'Something went wrong, please retry the command.',
                timestamp=True,
                color="red"
            )
            return
        trade_msg = await chan.send(f"{pref}t {user.mention}")
        trade_start_msg = await wait_for(
            chan, self.ctx, init_msg=trade_msg,
            check=lambda msg: poketwo_embed_cmd(
                msg, self.ctx, message, chan=chan,
                title_contains=f"Trade between {self.ctx.user.name} and {user.name}."
            ),
            timeout=120.0
        )
        if not trade_start_msg:
            self.logger.pprint(
                'Trade didn\'t start, please retry the command.',
                timestamp=True,
                color="red"
            )
            return
        await chan.send(f"{pref}t a pc {money}")
        await asyncio.sleep(random.uniform(2.0, 3.0))
        confirm_msg = await chan.send(f"{pref}t c")
        await wait_for(
            chan, self.ctx, event='message', init_msg=confirm_msg,
            check=lambda msg: poketwo_embed_cmd(
                msg, self.ctx, message, chan=chan,
                title_contains="Completed trade between "
                f"{self.ctx.user.name} and {user.name}."
            ),
            timeout=3.0
        )
        self.logger.pprint(
            f'Successfully gifted {int(money):,} credits to {user}.',
            timestamp=True,
            color="green"
        )

    @check_db
    @get_prefix
    @get_chan
    async def cmd_mass_sell(
        self, message: Message,
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Sell all your trash pokemon in the market.
        $```scss
        {command_prefix}mass_sell [IDs/Names/"Dupes"]
        ```$

        @🌟 Auto add a list of pokemon to market for sale.
        Can accept either a list of pokemon ids (seperated by spaces) or "dupes".
        Dupes are all the duplicate pokemons more than the max_duplicates limit.
        Pokemons with IV greater than iv_threshold won't be considered as dupes.
        Similarly, Priority, Legendary, Shiny and Nicknamed ones are excluded too.
        Credits scale with level (linearly) and total IV% (quadratically).@

        ~To list the pokemons 1200, 121, and 69:
            ```
            {command_prefix}mass_sell 1200 121 69
            ```
        To list all the duplicate pokemon:
            ```
            {command_prefix}mass_sell dupes
            ```
        To list all the Trubbish and Magikarps:
            ```
            {command_prefix}mass_sell Trubbish Magikarp
            ```
        To list the pokemons 1200 and 69 along with all Ratattas:
            ```
            {command_prefix}mass_sell 1200 Ratatta 69
            ```~
        """
        pref = kwargs["pref"]
        chan = kwargs["chan"]
        args = args or ["dupes"]
        listing = self.__get_listing(args, ids_only=False)
        if len(listing) == 0:
            self.logger.pprint(
                "Did not find any pokemons matching the trash conditions.",
                timestamp=True,
                color="yellow"
            )
            return
        listing = sorted(listing, key=lambda x: x["pokeid"], reverse=True)
        status = await self.__lister(message, pref, chan, listing)
        if status != -1:
            self.logger.pprint(
                "Successfully listed all the specified pokemons.\n",
                timestamp=True,
                color="green"
            )

    @check_db
    @get_prefix
    @get_chan
    async def cmd_mass_release(
        self, message: Message,
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Release all your trash pokemon into the wild.
        $```scss
        {command_prefix}mass_release [IDs/Names/"Dupes"]
        ```$

        @🌟 Autorelease a list of pokemon.
        Can accept either a list of pokemon ids (seperated by spaces) or "dupes".
        Dupes are all the duplicate pokemons more than the max_duplicates limit.
        Pokemons with IV greater than iv_threshold won't be considered as dupes.
        Similarly, Priority, Legendary, Shiny and Nicknamed ones are excluded too.@

        ~To release the pokemons 1200, 121, and 69:
            ```
            {command_prefix}mass_release 1200 121 69
            ```
        To release all the duplicate pokemon (default):
            ```
            {command_prefix}mass_release dupes
            ```
        To release all the Trubbish and Magikarps:
            ```
            {command_prefix}mass_release Trubbish Magikarp
            ```
        To release the pokemons 1200 and 69 along with all Ratattas:
            ```
            {command_prefix}mass_release 1200 Ratatta 69
            ```~
        """
        pref = kwargs["pref"]
        chan = kwargs["chan"]
        args = args or ["dupes"]
        numbers = self.__get_listing(args, ids_only=True)
        numbers = sorted(numbers, key=int, reverse=True)
        numlist = [
            numbers[i:i+25]
            for i in range(0, len(numbers), 25)
        ]
        released = []
        for numbers in numlist:
            num_str = ' '.join(numbers)
            rls_msg = await chan.send(f"{pref}release {num_str}")
            desc_msg = await wait_for(
                chan, self.ctx, init_msg=rls_msg,
                check=lambda msg: poketwo_reply_cmd(
                    msg, self.ctx, message, chan=chan,
                    contains="release"
                )
            )
            if not desc_msg:
                self.logger.pprint(
                    "Did not receive any response from Poketwo.",
                    timestamp=True,
                    color="yellow"
                )
                continue
            desc = desc_msg.content
            dangers = [
                self.logger.wrap(pokemon, color=["bold", "red"])
                for pokemon in (
                    self.ctx.legendaries +
                    self.ctx.configs['priority']
                )
                if pokemon in desc
            ]
            if any(dangers):
                self.logger.pprint(
                    f"WOAH! Almost deleted {', '.join(dangers)}!",
                    timestamp=True,
                    color="red"
                )
                return
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await desc_msg.buttons['Confirm'].click()
            confirmation = await wait_for(
                chan, self.ctx, init_msg=desc_msg,
                check=lambda msg: poketwo_reply_cmd(
                    msg, self.ctx, message, chan=chan,
                    contains={"Aborted", "released"}
                )
            )
            if "released" in confirmation.content:
                self.database.delete_caught([
                    int(number)
                    for number in numbers
                ])
                released.extend(numbers)
            await asyncio.sleep(random.uniform(2.5, 3.0))
        if released:
            self.logger.pprint(
                "Successfully Released all the specified pokemons.",
                timestamp=True,
                color="green"
            )
        else:
            self.logger.pprint(
                "Did not find any pokemons matching the trash conditions.",
                timestamp=True,
                color="yellow"
            )

    @check_db
    @get_prefix
    @get_chan
    async def cmd_autofav(
        self, message: Message,
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Add pokemons with IV above specified percentage to favorites list.
        $```scss
        {command_prefix}autofav [iv] [--filters]
        ```$

        @Automatically favorite all pokemons with IVs greater than specified IV.
        By default iv_theshold in the configs will be used as IV.
        If poketwo filters are provided, it will populate pokemons based \
            on the search.
        Otherwise it will use IDs from that local database.
        In that case, make sure to use
        `{command_prefix}pokelog` before using this command.@

        ~To add all pokemons with IVs above 75 to fav:
            ```
            {command_prefix}autofav --iv >75
            ```
        To add all pokemons with IVs above 70 (default in configs) to fav:
            ```
            {command_prefix}autofav
            ```
        To add all legendary and mythical pokemons to fav:
            ```
            {command_prefix}autofav --leg --myth
            ```~
        """
        pref = kwargs["pref"]
        chan = kwargs["chan"]
        added = 0
        if kwargs:
            for key in ("pref", "chan", "mentions"):
                kwargs.pop(key)
            kwarg_str = ""
            if kwargs:
                for kwarg, val in kwargs.items():
                    kwarg_str += f" --{kwarg}"
                    if val is not True:
                        kwarg_str += f" {val}"
            fav_msg = await chan.send(f"{pref}favall {kwarg_str}")
            reply = await wait_for(
                chan, self.ctx, init_msg=fav_msg,
                check=lambda msg: poketwo_reply_cmd(
                    msg, self.ctx, message, chan=chan,
                    contains="sure you want to **favorite**"
                ),
                timeout=5.0
            )
            added = 0
            if reply:
                await reply.buttons['Confirm'].click()
                reply = await wait_for(
                    chan, self.ctx, init_msg=reply,
                    check=lambda msg: poketwo_reply_cmd(
                        msg, self.ctx, message, chan=chan,
                        contains="Favorited"
                    ),
                    timeout=5.0
                )
            if reply:
                added = int(
                    re.findall(
                        r'your\s(\d+)\sunfavorited',
                        reply.content
                    )[0]
                )
        else:
            iv_min = self.ctx.configs['iv_threshold']
            favs = self.database.fetch_query(iv_min=iv_min, order_by='-iv')
            for fav in favs:
                success = await self.__add_fav(message, pref, chan, fav)
                if success:
                    added += 1
        if added:
            self.logger.pprint(
                "Finished adding all the pokemons with "
                "specified condition to favorites.\n"
                f"Added Pokemons: {added}",
                timestamp=True,
                color="green"
            )
            return
        self.logger.pprint(
            "Couldn't add any pokemons to favorites, try again later.",
            timestamp=True,
            color="yellow",
        )

    @get_prefix
    @get_chan
    async def cmd_autocandy(
        self, message: Message,
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Buy Rare candies to level up your pokemons.
        $```scss
        {command_prefix}autocandy [level]
        ```$

        @Computes level difference and checks balance to automatically
        buy sufficient rare candies for a pokemon.
        If a level is given as arg, the remaining levels will use this
        as the treshold instead of 100.
        If you don't have enough credits to buy all the required RCs,
        it will buy as many as possible.@

        ~To buy RCs to level your pokemon to level **100** (Max Level):
            ```
            {command_prefix}autocandy
            ```
        To buy RCs to level your pokemon to level **50**:
            ```
            {command_prefix}autocandy 50
            ```
        """
        pref = kwargs["pref"]
        chan = kwargs["chan"]
        info = await self.curr_poke_info(message, pref, chan)
        curr_level = int(
            info.embeds[0].title.lower().split('level ')[1].split(' ')[0]
        )
        total = 100
        if args and args[0].isdigit():
            total = min(100, int(args[0]))
            if total <= curr_level:
                self.logger.pprint(
                    "Please enter a higher threshold for level.",
                    timestamp=True,
                    color="red"
                )
                return
        rem_level = total - curr_level
        await asyncio.sleep(random.uniform(2.5, 3.0))
        shop_msg = await chan.send(f"{pref}shop 1")
        shop = await wait_for(
            chan, self.ctx, init_msg=shop_msg,
            check=lambda msg: poketwo_embed_cmd(
                msg, self.ctx, message,
                chan=chan, title_contains="Shop"
            )
        )
        bal = int(
            shop.embeds[0].title.split(
                ' Pokécoins'
            )[0].split(' ')[-1].replace(',', '')
        )
        options = shop.embeds[0].fields
        candy = [
            option.name
            for option in options
            if 'rare cand' in option.name.lower()
        ][0]
        candy_rate = int(
            candy.lower().split('– ')[1].split(' ')[0]
        )
        quantity = min(
            floor(bal / candy_rate),
            rem_level
        )
        if quantity == 0:
            await send_embed(
                message.channel,
                embed=get_embed(
                    f"{self.ctx.user.mention}, you cannot afford "
                    "any Rare Candy.",
                    embed_type="warning"
                )
            )
            return
        await asyncio.sleep(random.uniform(2.5, 3.0))
        buy_msg = await chan.send(f"{pref}buy rare candies {quantity}")
        result = await wait_for(
            chan, self.ctx, init_msg=buy_msg,
            check=lambda msg: poketwo_embed_cmd(
                msg, self.ctx, message,
                chan=chan
            )
        )
        if "Congratulations" in result.embeds[0].title:
            name = result.embeds[0].description.split(
                'Your '
            )[1].split(' is')[0]
            level = result.embeds[0].description.split(' ')[-1]
            self.logger.pprint(
                f"Successfully auto-leveled {name} to level {level}",
                timestamp=True,
                color="green"
            )

    async def curr_poke_info(
        self, message: Message,
        pref: str, chan: TextChannel
    ):
        """
        Get the info message for current pokemon.
        """
        info_msg = await chan.send(f"{pref}info")
        info = await wait_for(
            chan, self.ctx, init_msg=info_msg,
            check=lambda msg: poketwo_embed_cmd(
                msg, self.ctx, message,
                chan=chan, footer_contains="Displaying"
            )
        )
        return info

    async def get_pokes(
        self, message: Message,
        pref: str, chan: TextChannel,
        ids_only: bool = False, **kwargs
    ):
        """
        Polls poketwo to get the favorite pokemon IDs.
        """
        kwargs.pop("mentions", None)
        kwarg_str = ""
        if kwargs:
            for kwarg, val in kwargs.items():
                kwarg_str += f" --{kwarg}"
                if val is not True:
                    kwarg_str += f" {val}"
        query_msg = await chan.send(f"{pref}pokemon {kwarg_str}")
        reply = await wait_for(
            chan, self.ctx, init_msg=query_msg,
            check=lambda msg: poketwo_embed_cmd(
                msg, self.ctx, message, chan=chan,
                title_contains="Your pokémon"
            ),
            timeout=5.0
        )
        if not reply:
            no_pokes = await chan.history().find(
                lambda msg: poketwo_reply_cmd(
                    msg, self.ctx, message, chan=chan,
                    contains="No pokémon found."
                )
            )
            if no_pokes:
                self.logger.pprint(
                    "You don't have any pokemons in the specified list.",
                    timestamp=True,
                    color="red"
                )
                return []
            self.logger.pprint(
                "Poketwo seems to be unresponsive right now, try again later.",
                timestamp=True,
                color="red"
            )
            return []
        pokemons = reply.embeds[0].description.splitlines()
        numlist = [
            log_formatter(
                self.ctx, pokemon
            )["pokeid"] if ids_only
            else log_formatter(self.ctx, pokemon)
            for pokemon in pokemons
        ]
        page_patt = r'entries \d+\–(\d+) out of (\d+)'
        page_match = re.search(page_patt, reply.embeds[0].footer.text)
        while page_match.group(1) != page_match.group(2):
            delme = await chan.send(f"{pref}n")
            reply = await wait_for(
                chan, self.ctx, event='message', init_msg=delme,
                check=lambda msg: poketwo_embed_cmd(
                    msg, self.ctx, message, chan=chan,
                    title_contains="Your pokémon"
                ),
                timeout=3.0
            )
            if not reply:
                self.logger.pprint(
                    "Didn't get a response from Poketwo in time.\n"
                    "Retry the trade command.",
                    color="yellow",
                    timestamp=True
                )
                return numlist
            page_patt = r'entries \d+\–(\d+) out of (\d+)'
            page_match = re.search(page_patt, reply.embeds[0].footer.text)
            pokemons = reply.embeds[0].description.splitlines()
            await delme.delete()
            numlist += [
                log_formatter(
                    self.ctx, pokemon
                )["pokeid"] if ids_only
                else log_formatter(self.ctx, pokemon)
                for pokemon in pokemons
            ]
            if len(pokemons) < 20:
                break
            await asyncio.sleep(random.uniform(1.0, 2.0))
        return numlist

    async def reindex_pk2(
        self, message: Message,
        pref: str, chan: TextChannel
    ):
        """
        Runs poketwo's reindex command.
        """
        reidx_msg = await chan.send(f"{pref}reindex")
        await wait_for(
            chan, self.ctx, init_msg=reidx_msg,
            check=lambda msg: poketwo_reply_cmd(
                msg, self.ctx, message, chan=chan,
                contains="reindexed"
            )
        )

    def __get_listing(self, args: List[str], ids_only: bool = False):
        cols = ["pokeid"] if ids_only else ["pokeid", "name", "iv", "level"]
        if "dupes" in (arg.lower() for arg in args):
            junk = self.database.get_trash(
                avoid=list(
                    map(
                        lambda x: x.title(),
                        self.ctx.configs["priority"]
                    )
                ),
                iv_threshold=float(self.ctx.configs["iv_threshold"]),
                max_dupes=int(self.ctx.configs["max_duplicates"]),
                output_cols=cols
            )
            listing = junk[:]
        else:
            listing = []
            for arg in args:
                if not arg.isdigit():
                    junk = self.database.get_trash(
                        name=arg, avoid=list(
                            map(
                                lambda x: x.title(),
                                self.ctx.configs["priority"]
                            )
                        ),
                        iv_threshold=float(self.ctx.configs["iv_threshold"]),
                        max_dupes=int(self.ctx.configs["max_duplicates"]),
                        output_cols=cols
                    )
                    listing.extend(junk)
                else:
                    listing.extend(
                        self.database.fetch_query(
                            pokeid=int(arg),
                            output_cols=cols
                        )
                    )
        if ids_only:
            listing = [
                str(mon["pokeid"])
                for mon in listing
            ]
        return listing

    async def __get_bal(self, message, pref, chan):
        bal_msg = await chan.send(f"{pref}bal")
        bal = await wait_for(
            chan, self.ctx, init_msg=bal_msg,
            check=lambda msg: poketwo_embed_cmd(
                msg, self.ctx, message, chan=chan,
                title_contains=f"{self.ctx.user.name}'s balance"
            ),
            timeout=5.0
        )
        if not bal:
            return None
        return bal.embeds[0].fields[0].value.replace(",", "")

    async def __add_fav(
        self, message: Message,
        pref: str, chan: TextChannel,
        fav: Dict
    ) -> bool:
        pokeid = fav["pokeid"]
        name = fav["name"]
        fav_msg = await chan.send(f"{pref}fav {pokeid}")
        reply = await wait_for(
            chan, self.ctx, init_msg=fav_msg,
            check=lambda msg: poketwo_reply_cmd(
                msg, self.ctx, message,
                chan=chan, contains=[name, "fav"]
            ),
            timeout=3.0
        )
        await asyncio.sleep(random.uniform(1.5, 2.0))
        if reply:
            self.logger.pprint(
                f"Succesfully added {name} ({pokeid}) to favorites.",
                timestamp=True,
                color="green"
            )
            return True
        return False

    async def __arg2ids(self, message: Message, args: List[str]):
        numlist = []
        for arg in args:
            if arg.isdigit():
                numlist.append(arg)
                continue
            warn_user = True
            name = arg.title()
            results = self.database.fetch_query(
                output_cols=["pokeid", "category", "nickname", "iv"],
                name=name
            )
            for res in results:
                if all([
                    any([
                        res["iv"] >= self.ctx.configs["iv_threshold"],
                        res["category"] != "common",
                        res["nickname"] is not None
                    ]),
                    warn_user
                ]):
                    reply = await self.__warn_user(message, name, res)
                    if any(
                        word in reply.content.lower()
                        for word in ["y", "yes"]
                    ):
                        emb = get_embed(
                            "Alright, adding it to the list.",
                            embed_type="info"
                        )
                        await send_embed(message.channel, embed=emb)
                    elif any(
                        word in reply.content.lower()
                        for word in ["a", "all"]
                    ):
                        emb = get_embed(
                            "Alright, this warning will be disabled "
                            "in this trade session.",
                            embed_type="info"
                        )
                        await send_embed(message.channel, embed=emb)
                        warn_user = False
                    else:
                        emb = get_embed(
                            "Alright, not adding it to the list.",
                            embed_type="info"
                        )
                        await send_embed(message.channel, embed=emb)
                        continue
                numlist.append(res["pokeid"])
        return numlist

    async def __warn_user(
        self, message: Message,
        name: str, res: Dict
    ):
        nick = (
            ' and nickname ' + res['nickname']
            if res['nickname']
            else ''
        )
        catog = res['category'].title()
        emb = get_embed(
            f"This **{name.title()}** is a **`{catog}`** "
            "pokemon with:\n"
            f"**IV**: `{res['iv']}`{nick}\n"
            "Are you sure you want to trade it away?\n"
            "Reply with `yes` or `all` to ignore this check.",
            embed_type="warning",
            title="This pokemon seems valuable..."
        )
        warn_msg = await message.channel.send(
            content=f"{message.author.mention}",
            embed=emb
        )
        reply = await wait_for(
            message.channel, self.ctx, init_msg=warn_msg,
            check=lambda msg: user_check(msg, message),
            timeout="infinite"
        )
        return reply

    async def __get_all_ids(self, message: Message):
        all_pokes = self.database.fetch_query(output_cols=["pokeid"])
        emb = get_embed(
                "You are using trade without any arguments!\n"
                "This will trade away all the pokemons except "
                "the one with ID 1.\n"
                "Reply with `yes` to proceed.",
                embed_type="warning",
                title="Trade Everything Away??"
            )
        warn_msg = await send_embed(message.channel, embed=emb)
        reply = await wait_for(
                message.channel, self.ctx, init_msg=warn_msg,
                check=lambda msg: user_check(msg, message),
                timeout="infinite"
            )
        if all(
            word not in reply.content.lower()
            for word in ["y", "yes"]
        ):
            emb = get_embed(
                    f"Check out {self.ctx.prefix}help trade if required.",
                    embed_type="info",
                    title="Trade Cancelled."
                )
            await send_embed(message.channel, embed=emb)
            return
        return [
            poke["pokeid"]
            for poke in all_pokes
            if poke["pokeid"] != 1
        ]

    async def __lister(
        self, message: Message,
        pref: str, chan: TextChannel,
        listing: List[Dict]
    ):
        def get_price(lvl: int, _iv: float):
            price = sqrt(
                (lvl * max(50, _iv) + _iv ** 2) / 2
            )
            return f"{round(price)}"

        # pylint: disable=cell-var-from-loop
        for poke in listing:
            price = get_price(poke['level'], poke['iv'])
            mkt_msg = await chan.send(
                f"{pref}market list {poke['pokeid']} {price}"
            )
            desc_msg = await wait_for(
                chan, self.ctx, init_msg=mkt_msg,
                check=lambda msg: poketwo_reply_cmd(
                    msg, self.ctx, message, chan=chan,
                    contains=[str(poke['pokeid']), str(price)]
                )
            )
            if not desc_msg:
                self.logger.pprint(
                    f"Failed to list {poke['name']} ({poke['pokeid']})",
                    timestamp=True,
                    color="yellow"
                )
                continue
            desc = desc_msg.content
            dangers = [
                self.logger.wrap(pokemon, color=["bold", "red"])
                for pokemon in (
                    self.ctx.legendaries +
                    self.ctx.configs['priority']
                )
                if pokemon in desc
            ]
            if any(dangers):
                self.logger.pprint(
                    f"WOAH! Almost deleted {', '.join(dangers)}!",
                    timestamp=True,
                    color="red"
                )
                return -1
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await desc_msg.buttons['Confirm'].click()
            confirmation = await wait_for(
                chan, self.ctx, init_msg=desc_msg,
                check=lambda msg: poketwo_reply_cmd(
                    msg, self.ctx, message, chan=chan,
                    contains={"Listed", "Aborted"}
                )
            )
            if not confirmation:
                await asyncio.sleep(1.0)
                confirmation = await chan.history(limit=5).find(
                    predicate=lambda msg: poketwo_reply_cmd(
                        msg, self.ctx, message, chan=chan,
                        contains={"Listed", "Aborted"}
                    )
                )
            if "Listed" in confirmation.content:
                self.database.delete_caught(poke["pokeid"])
            await asyncio.sleep(random.uniform(2.0, 2.5))

    # pylint: disable=too-many-arguments
    async def __trade(
        self, message: Message,
        user: Member, pref: str,
        chan: TextChannel, numbers: List[int]
    ):
        trade_msg = await chan.send(f"{pref}t {user.mention}")
        reply = await wait_for(
            chan, self.ctx, init_msg=trade_msg,
            check=lambda msg: poketwo_embed_cmd(
                msg, self.ctx, message, chan=chan,
                title_contains="Trade between "
                f"{self.ctx.user.name} and {user.name}."
            ),
            timeout=5.0
        )
        if not reply:
            return False
        tradelist = " ".join(str(num) for num in numbers)
        if len(tradelist.split("pc")) > 1:
            nums, creds = (
                inp.strip()
                for inp in tradelist.split("pc")[:2]
            )
            await chan.send(f"{pref}t a {nums}")
            if creds:
                await chan.send(f"{pref}t a pc {creds}")
        else:
            await chan.send(f"{pref}t a {tradelist}")
        await asyncio.sleep(random.uniform(4.0, 5.0))
        confirm_msg = await chan.send(f"{pref}t c")
        reply = await wait_for(
            chan, self.ctx, event='message', init_msg=confirm_msg,
            check=lambda msg: poketwo_embed_cmd(
                msg, self.ctx, message, chan=chan,
                title_contains="Completed trade between "
                f"{self.ctx.user.name} and {user.name}."
            ),
            timeout=20.0
        )
        if reply:
            await asyncio.sleep(random.uniform(5.0, 5.5))
            return True
        return False
