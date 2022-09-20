"""
Market Commands Module
"""


# pylint: disable=too-many-locals, too-many-arguments, too-many-lines
# pylint: disable=too-many-function-args, unused-argument

import asyncio
import contextlib
import json
import random
import re
from datetime import datetime
from functools import wraps
from io import BytesIO
from math import ceil
import time
from typing import Callable, Dict, List, Optional

import discord
from discord import Message, TextChannel
from matplotlib import pyplot as plt
from matplotlib.ticker import MaxNLocator

from ..helpers.checks import (
    poketwo_embed_cmd, poketwo_reply_cmd,
    user_check
)
from ..helpers.utils import (
    get_embed, get_enum_embed, send_embed,
    wait_for
)
from .pokecommands import PokeCommands
from .basecommand import (
    get_chan, get_prefix, maintenance
)

COLORS = plt.rcParams["axes.prop_cycle"]()
plt.rcParams.update({'font.size': 14})


def get_modded_name(func: Callable):
    '''
    Appends Shiny to the name if shiny kwarg is provided.
    '''
    @wraps(func)
    def wrapped(self, message: Message, *args, **kwargs):
        name = kwargs.get("name")
        if kwargs.get("args", []):
            if kwargs["args"][0].lower() in ["track", "untrack", "plot"]:
                command = kwargs["args"][0].lower()
            else:
                command = "plot"
                kwargs["args"].append(command)
        else:
            command = "plot"
            kwargs["args"] = [command]
        if not name:
            if command.lower() == "plot":
                return func(self, message=message, *args, **kwargs)
            self.logger.pprint(
                "You need to provide a pokemon name.",
                color="yellow",
                timestamp=True
            )
            return None
        kwargs["modded_name"] = name
        if any(
            kwargs.get(sh, False)
            for sh in ["shiny", "sh"]
        ):
            kwargs["modded_name"] = f"shiny {name}"
        return func(self, message=message, *args, **kwargs)

    return wrapped


def check_tracked(func: Callable):
    '''
    Checks if tracked list is empty.
    '''
    @wraps(func)
    def wrapped(self, message: Message, *args, **kwargs):
        if kwargs.get("args", []):
            if kwargs["args"][0].lower() in ["track", "untrack", "plot"]:
                command = kwargs["args"][0].lower()
            else:
                command = "plot"
                kwargs["args"].append(command)
        else:
            command = "plot"
            kwargs["args"] = [command]
        if not all([
            len(self.tracked) == 0,
            command in ["untrack", "plot"]
        ]):
            return func(self, message=message, *args, **kwargs)
        self.logger.pprint(
            f"Your track list is empty.\n"
            f"Check out {self.ctx.prefix}help stocks.",
            color="yellow",
            timestamp=True
        )
        return None
    return wrapped


def check_sniped(func: Callable):
    '''
    Checks if snipe list is empty.
    '''
    @wraps(func)
    def wrapped(self, message: Message, *args, **kwargs):
        if not self.ctx.autosnipe:
            self.logger.pprint(
                "Autosnipe is not toggled on.",
                timestamp=True,
                color="yellow"
            )
            return None
        if kwargs.get("args", []):
            if kwargs["args"][0].lower() in ["add", "remove", "list"]:
                command = kwargs["args"][0].lower()
            else:
                command = "add"
                kwargs["args"].append(command)
        else:
            command = "add"
            kwargs["args"] = [command]
        if not all([
            len(self.sniped) == 0,
            command in ["remove", "list"]
        ]):
            return func(self, message=message, *args, **kwargs)
        self.logger.pprint(
            f"Your snipe list is empty.\n"
            f"Check out {self.ctx.prefix}help snipe.",
            color="yellow",
            timestamp=True
        )
        return None
    return wrapped


class MarketCommands(PokeCommands):
    '''
    Commands specifically dedicated towards market related command.
    Subclass of PokeCommands.
    They require DB access to get the guild_prefixes table.
    Examples: Flip, Snipe.
    '''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_balance = 0
        self.tracked = {}
        self.sniped = []

    @maintenance
    @get_chan
    async def cmd_flip(self, message: Message, **kwargs):
        """Instant price flipping for pokemons listed in market.
        $```scss
        {command_prefix}flip
            [--max_invest amount]
            [--name Name]
            [--shiny --leg --myth]
            [--price_diff amount]
        ```$

        @🌟 Quickly flip the prices of pokemons listed in the market
         based on desired conditions.
        You can pass poketwo filters like name, legendary, shiny, etc.
        Automatically verifies your balance to invest the chosen amount.@

        ~To flip the prices of cheapest pokemons:
            ```
            {command_prefix}flip --max_invest 100
            ```
        To flip the prices of the cheapest Shiny Pikachus:
            ```
            {command_prefix}flip --name pikachu --shiny --max_invest 10000
            ```
        To flip the prices of Arceus by 500% (you monster!):
            ```
            {command_prefix}flip --name Arceus --max_invest 10000000 --price_diff 500
            ```~
        """
        chan = kwargs.pop("chan")
        kwargs.pop("args", [])
        price_diff = int(kwargs.pop("price_diff", 50))
        max_invest = int(kwargs.pop("max_invest", 0))
        kwargs["order"] = "price+"
        if max_invest == 0:
            self.logger.pprint(
                "You need to provide a maximum amount to invest using --max_invest.",
                color="yellow",
                timestamp=True
            )
            return
        if self.current_balance > 0:
            balance = self.current_balance
        else:
            self.current_balance = balance = await self.__get_balance(message)
        if balance < max_invest:
            self.logger.pprint(
                "You do not have enough balance to invest that much.\n"
                f"Your balance: {balance} pc.",
                color="yellow",
                timestamp=True
            )
            return
        latest_id = await self.__get_latest_pokeid(message)
        mkt_data, _ = await self.__get_market_listing(
            message, channel=chan, **kwargs
        )
        invested = 0
        investments = []
        self.ctx.autocatcher_enabled = False
        for poke in mkt_data:
            if invested + poke["Credits"] <= max_invest:
                success = await self.__buy(message, **poke)
                if success:
                    latest_id += 1
                    poke["PokeId"] = latest_id
                    poke["SellFor"] = ceil(
                        poke["Credits"] * (100 + price_diff) / 100)
                    investments.append(poke)
                    invested += poke["Credits"]
                    self.current_balance -= poke["Credits"]
                continue
            break
        self.ctx.autocatcher_enabled = True
        returns = 0
        self.logger.pprint(
            f"Invested on {len(investments)} pokemons.",
            color="blue",
            timestamp=True
        )
        for poke in investments:
            success = await self.__sell(message, **poke)
            if success:
                returns += poke["SellFor"]
                name = poke['Name']
                if poke["Shiny"]:
                    name = f"Shiny {name}"
                self.logger.pprint(
                    f"Succesfully flipped {name} from "
                    f"{poke['Credits']} pc to {poke['SellFor']} pc!",
                    color="green",
                    timestamp=True
                )
        profit = f"{returns - invested} pc"
        self.logger.pprint(
            f"\nAmount Invested: {invested} pc.\n"
            f"Your stocks in the market: {returns} pc.\n"
            f"Estimated Profit: {self.logger.wrap(profit, color='bold')}",
            color="green",
            timestamp=False
        )

    @check_sniped
    @get_chan
    async def cmd_snipe(self, message: Message, **kwargs):
        """Autosniper for PokeTwo Market.
        $```scss
        {command_prefix}snipe [add]
            [--name Name]
            [--shiny --leg --myth]
            [--max_invest amount]
            [--interval seconds]
        {command_prefix}snipe [remove]
            [--name Name]
            [--shiny --leg --myth]
        {command_prefix}snipe list
        ```$

        @🌟 Automatically  nipe pokemons  from market,based on desired conditions.
        You can pass poketwo filters like name, legendary, shiny, etc.
        If no maximum investment is provided, the entire balance will be used.
        If no interval is provided, defaults to 5 minutes.
        DMs owner upon a succesfull snipe.@

        ~To snipe the cheapest Arcues you could afford:
            ```
            {command_prefix}snipe --name Arceus
            ```
        To snipe the cheapest Shiny Pikachus within a budget of 5000 pc:
            ```
            {command_prefix}snipe --name pikachu --shiny --max_invest 5000
            ```
        To snipe the Charizards listed for below 50c:
            ```
            {command_prefix}snipe --name charizard --max_poke_creds 50
            ```
        To monitor legendaries every 2 minutes:
            ```
            {command_prefix}snipe --leg --max_invest 5000 --interval 120
            ```
        To list your current snipes:
            ```
            {command_prefix}snipe list
            ```
        To remove a snipe from the list:
            ```
            {command_prefix}snipe remove
            ```~
        """
        chan = kwargs.pop("chan")
        args = kwargs.pop("args", [])
        valid_args = ["add", "remove", "list"]
        if args[0].lower() in valid_args[1:]:
            snipes = []
            coros = []
            sniped = self.sniped[:]
            for snp in sniped:
                snp_dict = {**snp}
                coros.append(snp_dict.pop("coro"))
                snipes.append(
                    f"```json\n{json.dumps(snp_dict, indent=3)}\n```"
                )
        if args[0].lower() == valid_args[1]:
            emb = get_enum_embed(
                snipes,
                title="Choose a snipe to remove:",
                custom_ext=True
            )
            emb_msg = await send_embed(message.channel, embed=emb)
            opt_msg = await wait_for(
                message.channel, self.ctx, init_msg=emb_msg,
                check=lambda msg: user_check(msg, message),
                timeout="infinite"
            )
            try:
                opt = int(opt_msg.content) - 1
                self.sniped.pop(opt)
                coros[opt].cancel()
                await send_embed(
                    message.channel,
                    embed=get_embed("Successfully removed it!")
                )
            except ValueError:
                await send_embed(
                    message.channel,
                    embed=get_embed(
                        "Got invalid input. Please retry.",
                        embed_type="error"
                    )
                )
            return
        if args[0].lower() == valid_args[2]:
            emb = get_enum_embed(
                snipes,
                title="Currently Being Sniped:",
                custom_ext=True
            )
            await send_embed(message.channel, embed=emb)
            return
        kwargs.pop("mentions", [])
        iv_min = float(kwargs.pop("iv_min", 0.0))
        max_invest = int(kwargs.pop("max_invest", 0))
        max_poke_creds = int(kwargs.pop("max_poke_creds", 0))
        invested = int(kwargs.pop("invested", 0))
        max_invest -= invested
        interval = float(kwargs.pop("interval", 5 * 60))
        if self.current_balance > 0:
            balance = self.current_balance
        else:
            self.current_balance = balance = await self.__get_balance(message)
        max_invest, max_poke_creds = self.__mkt_warn_user(
            max_invest, max_poke_creds, balance
        )
        self.ctx.task_tracker.register("snipe", self.__snipe)
        chan = kwargs.pop("channel", chan)
        coro = self.ctx.loop.create_task(
            self.__snipe(
                message, chan, interval,
                max_invest, iv_min, max_poke_creds,
                invested=invested, **kwargs
            )
        )
        shiny = any(
            kwargs.pop(sh, False)
            for sh in ["shiny", "sh"]
        )
        preopt = {
            "name": kwargs.get("name", None),
            "shiny": shiny,
            "iv_min": iv_min,
            "max_invest": max_invest,
            **kwargs
        }
        options = {
            **preopt,
            "coro": coro
        }
        existing = [
            (idx, opt)
            for idx, opt in enumerate(self.sniped)
            if {
                k: v
                for k, v in opt.items()
                if k != "coro"
            } == preopt
        ]
        if existing:
            idx, opt = existing[0]
            self.sniped[idx]["coro"] = coro
        else:
            self.sniped.append(options)

    @get_chan
    @get_modded_name
    @check_tracked
    async def cmd_stocks(
        self, message: Message,
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Track Price changes of Pokemons in PokeTwo Market.
        $```scss
        {command_prefix}stocks
            [track/untrack/plot]
            [--name Name]
            [--shiny]
            [--interval seconds]
        ```$

        @Monitor the price changes of chosen pokemon in the market.
        You can choose to track the Shiny variant exclusively.
        (:warning: You need to specify `--sh` while untracking a shiny.)
        If no interval is provided, defaults to 5 minutes.

        There are 3 options to choose from:
        ```md
        1. Track - Add a pokemon to track list.
        2. Untrack - Untrack a pokemon being tracked.
        3. Plot - Plot a graph showing the fluctuations in the prices.
        ```
        Defaults to `Plot` if no option is provided.@

        ~The add a Pikachu to the track list:
            ```
            {command_prefix}stocks track --name Pikachu
            ```
        To monitor the prices of Arceus every 10 seconds:
            ```
            {command_prefix}stocks track --name Arceus --interval 10
            ```
        To stop giving a damn about Ralts which you've been tracking:
            ```
            {command_prefix}stocks untrack --name Ralts
            ```
        To see the graph with the price fluctuations:
            ```
            {command_prefix}stocks
            ```~
        """
        command = args[0].lower()
        chan = kwargs["chan"]
        if command == "track":
            self.__stocks_track(message, kwargs, chan)
            return
        if command == "untrack":
            self.__stocks_untrack(kwargs)
            return
        if command == "plot":
            await self.__stocks_plot(message, kwargs)

    @get_chan
    @get_prefix
    async def __buy(self, message: Message, **kwargs) -> bool:
        pref = kwargs["pref"]
        chan = kwargs["chan"]
        mktid = kwargs["Mktid"]
        total_iv = kwargs["IV"]
        name = kwargs["Name"].lower()
        creds = str(kwargs["Credits"])
        buy_msg = await chan.send(f"{pref}m b {mktid}")
        reply = await wait_for(
            chan, self.ctx, init_msg=buy_msg,
            check=lambda msg: poketwo_reply_cmd(
                msg, self.ctx, message,
                chan=chan, contains={
                    name, str(total_iv), creds,
                    "longer", "find", "aborted"
                }
            ),
            timeout=2.0
        )
        if not reply:
            return False
        if any(
            phrase in reply.content.lower()
            for phrase in ["longer", "find"]
        ):
            self.logger.pprint(
                f"Someone outsniped the {name.title()} ({total_iv}%)!",
                color="yellow",
                timestamp=True
            )
            return False
        if "aborted" in reply.content.lower():
            return False
        if reply.buttons and 'Confirm' in reply.buttons:
            await reply.buttons['Confirm'].click()
        reply = await wait_for(
            chan, self.ctx, init_msg=reply,
            check=lambda msg: poketwo_reply_cmd(
                msg, self.ctx, message,
                chan=chan, contains={
                    "Aborted", "Purchased",
                    "longer", "find"
                }
            ),
            timeout=3.0
        )
        if not reply:
            return False
        if any(
            phrase in reply.content.lower()
            for phrase in ["longer", "find"]
        ):
            self.logger.pprint(
                f"Someone outsniped the {name.title()} ({total_iv}%)!",
                color="yellow",
                timestamp=True
            )
        return "purchased" in reply.content.lower()

    async def __dm_owner(
        self, remaining: int,
        cost_required: int,
        data: Dict
    ):
        name = data["Name"]
        if data["Shiny"]:
            name = f"Shiny {name}"
        level = data["Level"]
        total_iv = data["IV"]
        self.logger.pprint(
            f"Sniped a {name} for {cost_required} pc!\n"
            f"IV: {total_iv}%\tLevel: {level}",
            color="green",
            timestamp=True
        )
        emb = get_embed(
            title=f"**Sniped a {name}!**",
            content=f"Purchased it for **{cost_required} pc**.",
            color=7929600
        )
        emb.add_field(
            name="Level",
            value=level,
            inline=True
        )
        emb.add_field(
            name="IV",
            value=f"{total_iv}%",
            inline=True
        )
        emb.add_field(
            name="Investment Remaining",
            value=f"{remaining} pc",
            inline=True
        )
        emb.add_field(
            name="Current Poketwo Balance",
            value=f"{self.current_balance} pc",
            inline=True
        )
        emb.set_footer(
            text=f"Sniped from market at {datetime.now().strftime('%X')}."
        )
        with contextlib.suppress(discord.HTTPException):
            await send_embed(self.ctx.owner, embed=emb)

    @get_chan
    async def __get_market_listing(self, message: Message, **kwargs) -> list:
        chan = kwargs.pop("chan")
        shiny = kwargs.pop("sh", None)
        args = ["m", "s"]
        if shiny:
            args.append("--sh")
        interval = kwargs.pop("interval", 5 * 60)
        if interval:
            interval = float(interval)
        mkt_msg = await self.cmd_poke_exec(
            message,
            args=args,
            **kwargs
        )
        kwargs["chan"] = chan
        wait_failed = False
        try:
            done, pending = await self.__get_mkt_list(
                message, kwargs, chan,
                interval, mkt_msg
            )
            try:
                reply = done.pop().result()
                for future in pending:
                    future.cancel()
            except Exception:  # pylint: disable=broad-except
                return (None, False)
        except asyncio.TimeoutError:
            wait_failed = True
            history = chan.history(limit=10, after=mkt_msg)
            reply = None
            async for msg in history:
                reply = await history.find(
                    predicate=lambda msg: poketwo_embed_cmd(
                        msg, self.ctx, message,
                        chan=chan, title_contains="Pokétwo Marketplace",
                        description_contains=kwargs.get("name", "")
                    )
                )
                if poketwo_embed_cmd(
                    msg, self.ctx, message,
                    chan=chan, title_contains="Pokétwo Marketplace",
                    description_contains=kwargs.get("name", "")
                ):
                    reply = msg
                    break
            if not reply:
                return (None, True)
        if not reply:
            return (None, False)
        if len(reply.embeds) == 0:
            self.logger.pprint(
                "No listings found for the given condition.",
                color="yellow",
                timestamp=True
            )
            return (None, False)
        listing = reply.embeds[0].description.splitlines()
        mkt_data = []
        bad_chars = [r'\\xa0+', r'\*+', r'•+',
                     r'<+.+>+\s', r'\s\s+', '♂', '♀️']
        mkt_patt = r"`(?P<Mktid>.+)`.+Level\s(?P<Level>\d+)\s" + \
            r"(?P<Name>.+)\s(?P<IV>.+)\%\s(?P<Credits>.+)pc"
        for poke in listing:
            cleaned = poke
            for char in bad_chars:
                cleaned = re.sub(char, " ", cleaned)
            data = re.search(mkt_patt, cleaned).groupdict()
            data["Mktid"] = data["Mktid"].strip()
            data["Level"] = int(data["Level"])
            data["IV"] = float(data["IV"])
            data["Credits"] = int(data["Credits"].strip().replace(',', ''))
            data["Shiny"] = "✨" in cleaned
            mkt_data.append(data)
        return mkt_data, wait_failed

    async def __get_mkt_list(
        self, message: Message,
        kwargs: Dict, chan: TextChannel,
        interval: float, mkt_msg: Message
    ):
        done, pending = await asyncio.wait(
            [
                wait_for(
                    chan, self.ctx, init_msg=mkt_msg,
                    check=lambda msg: poketwo_embed_cmd(
                        msg, self.ctx, message,
                        chan=chan, title_contains="Pokétwo Marketplace",
                        description_contains=kwargs.get("name", "")
                    ),
                    timeout=interval
                ),
                wait_for(
                    chan, self.ctx, init_msg=mkt_msg,
                    check=lambda msg: poketwo_reply_cmd(
                        msg, self.ctx, message,
                        chan=chan, contains="No listing"
                    ),
                    timeout=interval
                )
            ],
            return_when=asyncio.FIRST_COMPLETED
        )
        return done, pending

    @get_prefix
    @get_chan
    async def __get_balance(self, message: Message, **kwargs) -> int:
        pref = kwargs["pref"]
        chan = kwargs["chan"]
        bal_msg = await chan.send(f"{pref}bal")
        reply = await wait_for(
            chan, self.ctx, init_msg=bal_msg,
            check=lambda msg: poketwo_embed_cmd(
                msg, self.ctx, message,
                chan=chan, title_contains="balance"
            ),
            timeout=3.0
        )
        await asyncio.sleep(0.5 + random.uniform(0.5, 1.0))
        emb = reply.embeds[0]
        bal = [
            field.value
            for field in emb.fields
            if field.name == "Pokécoins"
        ][0]
        return int(bal.replace(",", ""))

    @get_prefix
    @get_chan
    async def __get_latest_pokeid(self, message: Message, **kwargs) -> int:
        pref = kwargs["pref"]
        chan = kwargs["chan"]
        await self.reindex_pk2(
            message, pref, chan
        )
        info = await self.curr_poke_info(
            message, pref, chan
        )
        await asyncio.sleep(0.5 + random.uniform(0.5, 1.0))
        return int(
            re.match(
                r"Displaying\spokémon\s(\d+)\.",
                info.embeds[0].footer.text
            )[1]
        )

    async def __handle_snipe_buy(
        self, message: Message,
        interval: float, max_invest: int,
        invested: int, cdtn: str,
        attempts: int, investments: list,
        mkt_data: List[Dict]
    ):
        cost_required = mkt_data[0]["Credits"]
        for data in mkt_data:
            cost_required = data["Credits"]
            if cost_required + invested <= max_invest:
                success = await self.__buy(message, **data)
                if success:
                    investments.append(data)
                    self.current_balance -= data["Credits"]
                    invested += data["Credits"]
                    await self.__dm_owner(
                        (max_invest - invested),
                        cost_required, data
                    )
                    await asyncio.sleep(1.0 + random.uniform(0.5, 1.0))
        if investments:
            self.logger.pprint(
                f"[Attempt {attempts}] No luck yet for sniping{cdtn}. "
                f"Will retry in {interval} seconds.",
                color="blue",
                timestamp=True
            )
        return investments, invested

    def __mkt_warn_user(
        self, max_invest: int,
        max_poke_creds: int, balance: int
    ):
        if balance < max_invest:
            self.logger.pprint(
                "You do not have enough balance to invest that much.\n"
                f"Your balance of {balance} pc will be used as max_invest.",
                color="yellow",
                timestamp=True
            )
            max_invest = balance
        elif max_invest == 0:
            self.logger.pprint(
                "You have not provided a value for --max_invest.\n"
                f"Your balance of {balance} pc will be used as max_invest.",
                color="yellow",
                timestamp=True
            )
            max_invest = balance
        if max_poke_creds == 0:
            self.logger.pprint(
                "You have not provided a value for --max_poke_creds.\n"
                f"Your investment of {max_invest} pc will be used "
                "as max_poke_creds.",
                color="yellow",
                timestamp=True
            )
            max_poke_creds = max_invest
        return max_invest, max_poke_creds

    @get_chan
    @get_prefix
    async def __sell(self, message: Message, **kwargs) -> bool:
        pref = kwargs["pref"]
        chan = kwargs["chan"]
        pokeid = kwargs["PokeId"]
        total_iv = kwargs["IV"]
        name = kwargs["Name"].lower()
        sellfor = kwargs["SellFor"]
        add_msg = await chan.send(f"{pref}m add {pokeid} {sellfor}")
        reply = await wait_for(
            chan, self.ctx, init_msg=add_msg,
            check=lambda msg: poketwo_reply_cmd(
                msg, self.ctx, message,
                chan=chan, contains={
                    name, str(pokeid), str(total_iv),
                    str(sellfor), "aborted"
                }
            )
        )
        if "aborted" in reply.content.lower():
            return False
        await asyncio.sleep(0.5 + random.uniform(0.5, 1.0))
        y_msg = await chan.send("y")
        reply = await wait_for(
            chan, self.ctx, init_msg=y_msg,
            check=lambda msg: poketwo_reply_cmd(
                msg, self.ctx, message,
                chan=chan, contains={"Listed", "aborted"}
            )
        )
        await asyncio.sleep(1.0 + random.uniform(0.5, 1.0))
        if "aborted" in reply.content.lower():
            return False
        if "listed" in reply.content.lower():
            return True

    async def __snipe(
        self, message: Message,
        channel: TextChannel, interval: float,
        max_invest: int, iv_min: float,
        max_poke_creds: int, **kwargs
    ):
        cdtn = kwargs.get(
            "name",
            " the given snipe condition"
        )
        if cdtn:
            cdtn = f' {cdtn}'
        self.logger.pprint(
            f"Started the Snipe Monitor for{cdtn}.",
            color="blue",
            timestamp=True
        )
        attempts = 0
        invested = kwargs.pop("invested", 0)
        while self.ctx.autosnipe:
            if self.current_balance < (max_invest - invested):
                self.logger.pprint(
                    "Balance is lower than investment. Detaching snipe monitor.",
                    color="blue",
                    timestamp=True
                )
                return
            if invested >= max_invest:
                self.logger.pprint(
                    "Reached the Max Investment limit. Detaching snipe monitor.",
                    color="blue",
                    timestamp=True
                )
                return
            attempts += 1
            investments = []
            try:
                tstart = time.time()
                mkt_data, _ = await self.__get_market_listing(
                    message,
                    chan=channel,
                    interval=interval,
                    **kwargs
                )
                if not mkt_data:
                    self.logger.pprint(
                        f"[Attempt {attempts}] Failed to fetch market details, "
                        "retrying it.",
                        color="yellow",
                        timestamp=True
                    )
                    tend = time.time()
                    if (tend - tstart) < interval:
                        await asyncio.sleep(interval - (tend - tstart))
                    continue
            except Exception as excp:  # pylint: disable=broad-except
                self.logger.pprint(
                    str(excp),
                    color="red",
                    timestamp=True
                )
                self.logger.pprint(
                    f"[Attempt {attempts}] Failed to fetch market details, "
                    "retrying it.",
                    color="yellow",
                    timestamp=True
                )
                tend = time.time()
                if (tend - tstart) < interval:
                    await asyncio.sleep(interval - (tend - tstart))
                continue
            mkt_data = sorted(mkt_data, key=lambda x: x["Credits"])
            mkt_data = [
                poke
                for poke in mkt_data
                if all([
                    poke["IV"] > iv_min,
                    poke["Credits"] <= max_poke_creds
                ])
            ]
            if len(mkt_data) <= 0:
                continue
            investments, invested = await self.__handle_snipe_buy(
                message, interval, max_invest,
                invested, cdtn, attempts,
                investments, mkt_data
            )
            tend = time.time()
            if (tend - tstart) < interval:
                await asyncio.sleep(interval - (tend - tstart))
        return

    async def __stocks_plot(self, message, kwargs):
        delme = await send_embed(
            message.channel,
            embed=get_embed("Creating the graph, hold on. :hourglass:")
        )
        tracked = {
            kwargs["modded_name"]: self.tracked[kwargs["modded_name"]]
        } if kwargs.get(
            "modded_name", None
        ) else {**self.tracked}
        plt.figure(figsize=(10, 8))
        fig = plt.figure(figsize=(10, 8))
        num_subplots = len(tracked)
        for idx, (poke, data) in enumerate(tracked.items()):
            subp = fig.add_subplot(num_subplots, 1, idx + 1)
            subp.plot(
                range(len(data["price"])),
                data["price"],
                'o-', label=poke,
                color=next(COLORS)["color"]
            )
            for idx, price in enumerate(data["price"]):
                subp.annotate(
                    text=f'{price} pc',
                    xy=(idx, price),
                    horizontalalignment='center',
                    verticalalignment='center'
                )
            subp.yaxis.set_major_locator(MaxNLocator(integer=True))
            subp.legend()
            subp.set_ylabel("Pokecredits", fontsize=20)
            subp.axes.get_xaxis().set_visible(False)
        plt.tight_layout()
        byio = BytesIO()
        fig.savefig(byio)
        byio.seek(0)
        graph = discord.File(byio, "PokeTwo Stocks.png")
        await delme.delete()
        await message.channel.send(file=graph)

    def __stocks_untrack(self, kwargs):
        name = kwargs["modded_name"]
        poke = self.tracked.pop(name, None)
        if poke:
            poke["coro"].cancel()
            self.logger.pprint(
                f"Succesfully removed {name.title()} from tracked list.",
                color="green",
                timestamp=True
            )
        else:
            self.logger.pprint(
                f"You are not tracking a {name.title()}.\n"
                f"Check out {self.ctx.prefix}help stocks.",
                color="yellow",
                timestamp=True
            )

    def __stocks_track(self, message, kwargs, chan):
        modded_name = kwargs["modded_name"]
        name = kwargs["name"]
        shiny = any(
            kwargs.get(sh, False)
            for sh in ["shiny", "sh"]
        )
        mkt_kwargs = {
            "name": name,
            "sh": shiny,
            "lim": "1"
        }
        self.tracked[modded_name] = {
            "price": [],
            "mktid": [],
            "coro": None
        }
        interval = float(kwargs.get("interval", 5 * 60))
        coro = self.ctx.loop.create_task(
            self.__update_prices(
                message, chan,
                modded_name, interval,
                **mkt_kwargs
            )
        )
        self.tracked[modded_name]["coro"] = coro

    async def __update_prices(
        self, message: Message,
        channel: TextChannel,
        modded_name: str, interval: float,
        **mkt_kwargs
    ):
        i = 0
        while True:
            tstart = time.time()
            mkt_data, wait_failed = await self.__get_market_listing(
                message, chan=channel, **mkt_kwargs
            )
            price = mkt_data[0]["Credits"]
            mktid = mkt_data[0]["Mktid"]
            if mktid not in self.tracked[modded_name]["mktid"]:
                self.tracked[modded_name]["price"].append(price)
                self.tracked[modded_name]["mktid"].append(mktid)
            if i == 0:
                self.logger.pprint(
                    f"Succesfully added {modded_name.title()} to tracked list.",
                    color="green",
                    timestamp=True
                )
            i += 1
            tend = time.time()
            if not wait_failed and (tend - tstart) < interval:
                await asyncio.sleep(interval - (tend - tstart))
