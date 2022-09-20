"""
Compilation of utility functions for Pokeball.
"""

# pylint: disable=unused-argument, protected-access, too-many-locals

from __future__ import annotations
import asyncio
import contextlib
import html
import inspect
import json
import random
import re
from abc import ABC
from datetime import datetime
from itertools import chain
from typing import (
    Callable, Dict, Iterable,
    List, Optional, TYPE_CHECKING, Union
)

import aiohttp
import discord
import numpy as np

from discord import Embed
from discord.embeds import EmbedProxy

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from pokeball import PokeBall
    from discord import Message, TextChannel, User


class TaskTracker:
    """
    The tracker class for all command initiated async tasks.
    """

    # pylint: disable=too-few-public-methods

    def __init__(self, ctx: PokeBall):
        self.ctx = ctx

    def register(self, key: str, func: Callable):
        """
        Register a task as a class instance.
        """
        setattr(self, key, func)


class Snoozable(ABC):
    """
    Base Class for a snoozable task.
    """
    def __init__(
        self, ctx: PokeBall,
        controller: str, module: str,
        **kwargs
    ):
        self.ctx = ctx
        self.controller = controller
        self.module = getattr(ctx, f"{module}commands")

    def get_command(self, command: str):
        """
        Get the related command object.
        """
        module = getattr(
            self.ctx,
            "customcommands",
            None
        )
        if module:
            return getattr(
                module,
                f"cmd_{command}",
                getattr(self.module, f"cmd_{command}")
            )
        module = self.module
        return getattr(module, f"cmd_{command}")

    def get_coro(self, task: asyncio.Task):
        """
        Get the coroutine corresponding to the running task.
        """
        cmd_name = self.__class__.__name__.replace('Snooze', '').lower()
        command = self.get_command(cmd_name)
        sig = inspect.signature(
            getattr(self.ctx.task_tracker, cmd_name)
        )
        coro_locals = task._coro.cr_frame.f_locals
        kwargs = {
            **coro_locals.get("kwargs", {})
        }
        kwargs.update({
            param: coro_locals[param]
            for param in sig.parameters.keys()
            if param not in [
                "self", "kwargs"
            ] + list(kwargs.keys())
        })
        return command(**kwargs)


class SnoozeSpam(Snoozable):
    """
    Snoozable Spammer task
    """
    def __init__(self, ctx: PokeBall, **kwargs):
        super().__init__(
            ctx, controller="allow_spam", module="normal",
            **kwargs
        )


class SnoozeSnipe(Snoozable):
    """
    Snoozable Sniper task
    """
    def __init__(self, ctx: PokeBall, **kwargs):
        super().__init__(
            ctx, controller="autosnipe", module="market",
            **kwargs
        )


class OverriddenMessage(discord.Message):
    '''
    Overrides the message class to add a custom attribute.
    '''
    __slots__ = ()

    @property
    def buttons(self) -> Dict[str, discord.Button]:
        '''
        Returns the buttons in the message.
        '''
        return {
            button.label: button
            for actionrow in self.components
            for button in actionrow.children
            if isinstance(button, discord.Button)
        }


def get_formatted_time(tot_secs: int) -> str:
    """ Converts total seconds into a human readable format."""
    hours = divmod(tot_secs, 3600)
    minutes = divmod(hours[1], 60)
    seconds = divmod(minutes[1], 1)
    return (
        f"{int(hours[0]):02d} hours, {int(minutes[0]):02d} minutes"
        f" and {int(seconds[0]):02d} seconds"
    )


def get_ascii(msg: str) -> str:
    """Returns the ascii art for a text."""
    artmap = {
        "0": ".█████╗.\n██╔══██╗\n██║..██║\n██║..██║\n╚█████╔╝\n.╚════╝.",
        "1": "..███╗..\n.████║..\n██╔██║..\n╚═╝██║..\n███████╗\n╚══════╝",
        "2": "██████╗.\n╚════██╗\n..███╔═╝\n██╔══╝..\n███████╗\n╚══════╝",
        "3": "██████╗.\n╚════██╗\n.█████╔╝\n.╚═══██╗\n██████╔╝\n╚═════╝.",
        "4": "..██╗██╗\n.██╔╝██║\n██╔╝.██║\n███████║\n╚════██║\n.....╚═╝",
        "5": "███████╗\n██╔════╝\n██████╗.\n╚════██╗\n██████╔╝\n╚═════╝.",
        "6": ".█████╗.\n██╔═══╝.\n██████╗.\n██╔══██╗\n╚█████╔╝\n.╚════╝.",
        "7": "███████╗\n╚════██║\n....██╔╝\n...██╔╝.\n..██╔╝..\n..╚═╝...",
        "8": ".█████╗.\n██╔══██╗\n╚█████╔╝\n██╔══██╗\n╚█████╔╝\n.╚════╝.",
        "9": ".█████╗.\n██╔══██╗\n╚██████║\n.╚═══██║\n.█████╔╝\n.╚════╝.",
        "v": "██╗...██╗\n██║...██║\n╚██╗.██╔╝\n.╚████╔╝.\n..╚██╔╝..\n...╚═╝...",
        ".": "...\n...\n...\n...\n██╗\n╚═╝"
    }
    mapping = [artmap[ch] for ch in msg]
    art = '\n'.join(
        ''.join(var.split('\n')[i].replace(' ', '', 1) for var in mapping)
        for i in range(6)
    )

    art = '\t\t\t' + art.replace('\n', '\n\t\t\t')
    return art


def prettify_discord(
    ctx: PokeBall,
    iterable: List,
    mode: str = "guild"
) -> str:
    """Prettification for iterables like guilds and channels."""
    func = getattr(ctx, f"get_{mode}")
    return '\n\t'.join(
        ', '.join(
            f"{func(elem)} ({elem})"
            for elem in iterable[i:i + 2]
        )
        for i in range(0, len(iterable), 2)
    )


def get_embed(
    content: str = None,
    embed_type: str = "info",
    title: Optional[str] = None,
    **kwargs
) -> discord.Embed:
    """Creates a Discord Embed with appropriate color and provided info."""
    embed_params = {
        "info": {
            "name": "INFORMATION",
            "icon": ":information_source:",
            "color": 11068923
        },
        "warning": {
            "name": "WARNING",
            "icon": ":warning:",
            "color": 16763904
        },
        "error": {
            "name": "ERROR",
            "icon": "❌",
            "color": 11272192
        }
    }
    params = embed_params[embed_type]
    color = kwargs.pop('color', params["color"])
    icon = params['icon']
    if title and title.startswith('**'):
        title = title.lstrip('**')
        icon = f'**{icon}'
    return discord.Embed(
        title=f"{icon} {title or params['name']}",
        description=content,
        color=color,
        **kwargs
    )


def get_enum_embed(
    iterable: Iterable, embed_type: str = "info",
    title: str = None, custom_ext: bool = False,
    **kwargs
) -> discord.Embed:
    """Creates a Discord Embed with prettified iterable as description."""
    enum_str = '\n'.join(
        f"{i + 1}. {name}"
        for i, name in enumerate(iterable)
    )
    if not custom_ext:
        enum_str = f"```md\n{enum_str}\n```"
    return get_embed(
        enum_str,
        embed_type=embed_type,
        title=title,
        **kwargs
    )


def typowrite(pokename: str, typo_rate: int) -> str:
    """ Returns a smartly typo-ed text using common qwerty keyboard mistakes."""
    def get_target_letters(word):
        return [
            word[
                int(
                    np.clip(random.gauss(2, 4), 0, len(word) - 1)
                )
            ]
            for _ in range(random.choice([1, 2]))
        ]

    def typo_for_char(char):
        if char not in list(chain.from_iterable(qwerty)):  # For edge cases
            return char
        row = next(
            filter(lambda x: char in x, qwerty)
        )
        if row.index(char) in [0, len(row) - 1]:  # Boundary chars
            return char
        pad = random.choice([-1, 1])
        return row[row.index(char) + pad]

    qwerty = [
        ['0', '-', '='],
        ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', '['],
        ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', ';'],
        ['z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/']
    ]
    name = pokename.lower()
    proc2 = random.randint(1, 100)
    if typo_rate <= proc2:
        return name
    changes = [
        (char, typo_for_char(char), 1)
        for char in get_target_letters(name)
    ]
    for change in changes:
        name = name.replace(*change)
    return name


def log_formatter(ctx: PokeBall, pokemon: str) -> Dict:
    """ Converts a line from Poketwo's pokemon list to a dictionary."""
    if ctx.configs["clone_id"] != 716390085896962058:
        return {
            "name": None,
            "pokeid": 0,
            "level": 0,
            "iv": 0.0,
            "category": "common",
            "nickname": None
        }

    bad_chars = [r'\\xa0+', r'\*+', r'•+', r'<+.+>+\s', r'\s\s+', '♂', '♀️']
    pokeline = pokemon.replace(':heart:', '')
    for char in bad_chars:
        pokeline = re.sub(char, " ", pokeline)
    patt = r"`?\s?(\d+)`?\s(?:(✨)\s)?([\w\s\'\.\-:%]+)(?:\"(.+)\")?" + \
        r"(?:\s.+)?\sLvl\.\s(\d+)\s(\d+\.?\d+)%"
    searched = re.search(patt, pokeline)
    name = searched.group(3).title().strip()
    category = "common"
    if name in ctx.configs["priority"]:
        category = "priority"
    if name in ctx.legendaries:
        category = "legendary"
    if searched.group(2):
        category = "shiny"
    return {
            "name": name,
            "pokeid": int(searched.group(1)),
            "level": int(searched.group(5)),
            "iv": float(searched.group(6)) or 0.0,
            "category": category,
            "nickname": searched.group(4) or None
        }


async def sleep_handler(ctx: PokeBall):
    """Takes care of autosleeping based on provided sleep & wake times."""
    if not ctx.configs["autosleep"]:
        ctx.logger.pprint(
            "Autosleep seems to be disabled. "
            "Highly recommended to turn it on.\n",
            timestamp=True,
            color="yellow"
        )
        return
    sleep_time = float(ctx.configs["sleep_duration"])
    wake_time = float(ctx.configs["inter_sleep_delay"])
    stt = get_formatted_time(sleep_time)
    wtt = get_formatted_time(wake_time)
    snoozables = {
        "spam": SnoozeSpam(ctx),
        "snipe": SnoozeSnipe(ctx)
    }
    snoozed = []
    state_dict = {
        attr: getattr(ctx, attr)
        for attr in ["allow_spam", "autosnipe", "priority_only"]
    }
    while True:
        while ctx.catching:
            await asyncio.sleep(0.1)
        old_ts = datetime.now()
        await asyncio.sleep(wake_time)
        curr_ts = datetime.now()
        diff_secs = (curr_ts - old_ts).total_seconds()
        ltt = get_formatted_time(diff_secs)
        ctx.sleep = True
        snoozed = {
            task._coro.__name__: snoozables[task._coro.__name__].get_coro(task)
            for task in asyncio.all_tasks()
            if task._coro.__name__ in snoozables
        }

        snooze_str = ''
        if snoozed:
            snooze_str = "\n".join(
                f"{idx + 1}. {key}" for idx, key in enumerate(snoozed.keys())
            )

            snooze_str = f"Following will be paused:\n{snooze_str}\n"
        ctx.logger.pprint(
            f"Bot was previously active for {ltt}.\n"
            "Entering the sleep mode now.\n"
            f"{snooze_str}"
            "Temporarily switching autocatcher to Priority_only mode.\n",
            timestamp=True,
            color="blue"
        )
        ctx.allow_spam = False
        ctx.priority_only = True
        ctx.autosnipe = False
        await asyncio.sleep(sleep_time)
        ctx.logger.pprint(
            f"Slept for {stt}.\n"
            "Waking up and restoring previous state.\n"
            f"Will sleep again in {wtt}.\n",
            timestamp=True,
            color="blue"
        )
        for attr, state in state_dict.items():
            if attr not in ctx.user_changed.keys():
                setattr(ctx, attr, state)
            else:
                setattr(ctx, attr, ctx.user_changed[attr])
        for key, coro in snoozed.items():
            if getattr(ctx, snoozables[key].controller):
                ctx.logger.pprint(
                    f"{key.title()} was paused. Resuming it now.",
                    color="blue",
                    timestamp=True
                )
                ctx.loop.create_task(coro)
        ctx.sleep = False


async def get_message(sess: aiohttp.ClientSession) -> str:
    """Randomly retrieves text from one of the authless text APIs."""
    async def sv443():
        async with sess.get(
            "https://v2.jokeapi.dev/joke/Any?type=single"
        ) as resp:
            if resp.status > 399:
                joke = ""
            else:
                try:
                    joke = (await resp.json())["joke"]
                except KeyError:
                    return ""
        if len(joke) > 2000:
            return ''
        return joke

    async def appspot():
        async with sess.get(
            "https://official-joke-api.appspot.com/random_joke"
        ) as resp:
            joke = await resp.json()
            if any(
                word not in joke.keys()
                for word in ["setup", "punchline"]
            ):
                return ""
        return " ".join([
            joke["setup"], joke["punchline"]
        ]).replace("\n\n", "\n")

    async def doggo():
        async with sess.get(
            "https://dog.ceo/api/breeds/image/random"
        ) as resp:
            doggo_json = await resp.json()
            if any(
                word not in doggo_json.keys()
                for word in ["status", "message"]
            ):
                return ""
        if doggo_json["status"] != 'success':
            return ''
        return doggo_json["message"]

    async def chuck():
        async with sess.get(
            "http://api.icndb.com/jokes/random?escape=javascript"
        ) as resp:
            chuckjoke = await resp.json()
            if any(
                word not in chuckjoke.keys()
                for word in ["type", "value"]
            ):
                return ""
        if chuckjoke["type"] != "success":
            return ""
        try:
            return chuckjoke["value"]["joke"]
        except KeyError:
            return ""

    async def trivia():
        async with sess.get(
            "https://opentdb.com/api.php?amount=1"
        ) as resp:
            trivia_json = await resp.json()
            if any(
                word not in trivia_json.keys()
                for word in [
                    "response_code", "results",
                    "question", "correct_answer"
                ]
            ):
                return ""
        if trivia_json["response_code"] != 0:
            return ""
        trivia_json = trivia_json["results"][0]
        question = trivia_json["question"]
        answer = trivia_json["correct_answer"]
        return f"{question}\n{answer}"

    async def trump():
        async with sess.get(
            "https://www.tronalddump.io/random/quote"
        ) as resp:
            if resp.status >= 400:
                return ""
            trumpjoke = await resp.json()
        return trumpjoke.get("value", "")

    async def dadjoke():
        async with sess.get(
            "https://icanhazdadjoke.com/",
            headers={"Accept": "application/json"}
        ) as resp:
            joke_json = await resp.json()
            if any(
                word not in joke_json.keys()
                for word in ["status", "joke"]
            ):
                return ""
        if joke_json["status"] != 200:
            return ""
        return joke_json["joke"]

    msg = "....."
    endpoints = [
        sv443, appspot, doggo,
        chuck, trivia, trump, dadjoke
    ]
    for _ in range(10):
        if not endpoints:
            endpoints = [
                sv443, appspot, doggo,
                chuck, trivia, trump, dadjoke
            ]
        mode = random.choice(endpoints)
        try:
            msg = await mode()
            if msg == "":
                endpoints.remove(mode)
                continue
            break
        except Exception:  # pylint: disable=broad-except
            endpoints.remove(mode)
            continue
    return html.unescape(msg)


def parse_command(prefix: str, msg: str) -> Dict:
    """Parses a message to obtain the command, args and kwargs."""
    non_kwarg_str, *kwarg_str = msg.partition('--')
    main_sep_patt = (
        re.escape(prefix) +
        r'(?:(?P<Command>\S+)\s?)' +
        r'(?:(?P<Args>.+)\s?)*'
    )
    main_parsed_dict = re.search(main_sep_patt, non_kwarg_str).groupdict()
    if kwarg_str:
        main_parsed_dict["Kwargs"] = ''.join(kwarg_str)
    parsed = {
        'Args': [],
        'Kwargs': {},
        'Command': main_parsed_dict["Command"]
    }
    if main_parsed_dict["Args"]:
        parsed["Args"] = main_parsed_dict["Args"].rstrip(' ').split(' ')
    if main_parsed_dict.get("Kwargs", None):
        kwarg_patt = r'-{2}(?!-{2})[^-]+'
        kwargs = [
            kwarg.rstrip(' ')
            for kwarg in re.findall(
                kwarg_patt,
                main_parsed_dict["Kwargs"]
            )
        ]
        kwarg_dict = {}
        for kwarg in kwargs:
            key = kwarg.split(' ')[0].replace('--', '')
            val = True if len(
                kwarg.split(' ')
            ) == 1 else kwarg.replace(f'--{key} ', '')
            kwarg_dict[key] = val
        parsed["Kwargs"] = kwarg_dict
    return parsed


# pylint: disable=too-many-arguments
async def wait_for(
    chan: discord.TextChannel,
    ctx: PokeBall, event: str = "message",
    init_msg: Optional[discord.Message] = None,
    check: Callable = None,
    timeout: Optional[float] = None
):
    """
    Modified version of wait_for, which checks channel history upon timeout.
    If timeout='infinite', behaves as the original wait_for.
    """
    if not timeout:
        tmout = 3.0
    elif timeout == 'infinite':
        tmout = None
    else:
        tmout = timeout
    reply = None
    with contextlib.suppress(asyncio.TimeoutError):
        if event == "message_edit":
            _, reply = await ctx.wait_for(
                event,
                check=check,
                timeout=tmout
            )
        else:
            reply = await ctx.wait_for(
                event,
                check=check,
                timeout=tmout
            )
    if reply:
        reply.__class__ = OverriddenMessage
    return reply


async def check_for_updates(ctx: PokeBall):
    """
    Checks the remote Github repo for version update.
    """
    def get_mathver(ver):
        version_digits = ver.split('v')[1].split('.')
        lvd = len(version_digits)
        return sum(
            int(version_digits[i]) * pow(10, lvd - i)
            for i in range(lvd)
        )

    # Should not be called for every running bot if using advanced extension
    if ctx.advanced:
        return
    remote_ver_url = "https://raw.githubusercontent.com/Hyperclaw79/" + \
        "PokeBall-SelfBot/master/_version.json"
    try:
        async with ctx.sess.get(remote_ver_url) as resp:
            # Site returns wrong MIME type of text/plain for JSON
            data = json.loads(await resp.read())
        updates = data.get("updates", [])
        updates = "\n".join([
            f"{idx + 1}. {update}"
            for idx, update in enumerate(updates)
        ])
        if updates:
            updates = f"What's new:\n{updates}\n"
        remote_version = data["premium_version"]
        local_version = ctx.version
        if get_mathver(remote_version) > get_mathver(local_version):
            ctx.logger.pprint(
                "\nLooks like there is a new update available!\n"
                f"{updates}"
                "Download the latest version from the google drive link.\n"
                f"Your version: {local_version}\n"
                f"Available version: {remote_version}\n",
                color="green",
                timestamp=False
            )
    except Exception:  # pylint: disable=broad-except
        return


def get_rand_headers() -> Dict:
    """
    Returns a random User-Agent for aiohttp Session object.
    """
    browsers = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "AppleWebKit/537.36 (KHTML, like Gecko)",
        "discord/0.0.306",
        "Chrome/80.0.3987.132",
        "Discord/1.6.15",
        "Safari/537.36",
        "Electron/7.1.11"
    ]
    return {
        "User-Agent": ' '.join(
            set(
                random.choices(
                    browsers,
                    k=random.randint(1, len(browsers))
                )
            )
        ),
        "Referer": "https://discordapp.com",
        "Origin": "https://discordapp.com"
    }


def get_modules(ctx: PokeBall) -> List[Callable]:
    """
    Returns a list of all the commands.
    """
    return [
        getattr(ctx, comtype)
        for comtype in dir(ctx)
        if all([
            comtype.endswith('commands'),
            comtype != "load_commands"
        ])
    ]


async def send_embed(
    messagable: Union[User, TextChannel],
    embed: Embed,
    **kwargs
) -> Message:
    """
    Override the embed messages to convert embeds to content.
    """
    kwargs = __override_embed(embed, kwargs)
    msg = await messagable.send(**kwargs)
    return msg


async def edit_embed(
    message: Message,
    embed: Embed,
    **kwargs
) -> Message:
    """
    Override the embed messages to convert embeds to content.
    """
    kwargs = __override_embed(embed, kwargs)
    msg = await message.edit(**kwargs)
    return msg


def __override_embed(embed, kwargs):
    def pad_content(content):
        return '\n' if content else ''

    def check_not_empty(part):
        return (
            part is not None
            and not isinstance(part, EmbedProxy)
        )

    content = kwargs.pop("content", "") or ""
    if check_not_empty(embed.title):
        title = (
            embed.title if embed.title.startswith("**")
            else f"**{embed.title}**"
        )
        content += f"{pad_content(content)}{title}"
    if check_not_empty(embed.description):
        content += f"{pad_content(content)}{embed.description}"
    if check_not_empty(embed.fields):
        for field in embed.fields:
            if all([
                check_not_empty(field.name),
                check_not_empty(field.value)
            ]):
                field_name = (
                    field.name if field.name.startswith("**")
                    else f"**{field.name}**"
                )
                content += f"{pad_content(content)}{field_name}\n{field.value}"
    if check_not_empty(embed.footer):
        content += f"{pad_content(content)}{embed.footer.text}"
    if check_not_empty(embed.image):
        content += f"{pad_content(content)}{embed.image.url}"
    if check_not_empty(embed.thumbnail):
        content += f"{pad_content(content)}{embed.thumbnail.url}"
    if check_not_empty(embed.url):
        content += f"{pad_content(content)}{embed.url}"
    kwargs['content'] = content
    return kwargs
