"""
Pokeball Selfbot Poketwo Automation
This specific selfbot was designed to automatically catch pokemon spawned on Discord by Poketwo bot.
It also offers other utility functions to automate features like trading, releasing, id search, etc.
Currently the autocatcher is powered by AI making it possible to autocatch pokemons on multiple bots
like PokeTwo, PokeRealm, etc.
"""  # noqa: E501

# pylint: disable=no-member, too-many-instance-attributes
# pylint: disable=unused-argument, protected-access

import asyncio
import contextlib
import importlib
import json
import os
import random
import re
import sys
import traceback
from datetime import datetime
from itertools import chain

import aiohttp
import discord

from scripts.base.dbconn import DBConnector
from scripts.helpers.logger import CustomLogger
from scripts.helpers.stats_monitor import StatsMonitor
from scripts.helpers.utils import (
    OverriddenMessage, SnoozeSpam, TaskTracker, check_for_updates,
    get_ascii, get_formatted_time,
    get_rand_headers, parse_command,
    prettify_discord, sleep_handler
)


class PokeBall(discord.Client):
    """
    The main class for Pokeball Selfbot.
    """
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.version = "v8.5.0"
        for key, value in kwargs.items():
            self.__setattr__(key, value)
        with open(self.pokeclasses_path, encoding='utf-8') as pc_file:
            self.pokenames = pc_file.read().splitlines()
        with open(self.pokeranks_path, encoding='utf-8') as pr_file:
            self.pokeranks = json.load(pr_file)
        self.legendaries = list(chain.from_iterable(self.pokeranks.values()))
        # Defaults
        self.active_channels = []
        self.allow_spam = False
        self.catching = False
        self.advanced = False
        self.ready = False
        self.start_time = datetime.now()
        self.locked_channels = []
        self.caught_pokemons = 0
        self.sleep = False
        self.autosnipe = True
        self.sess = None
        self.catcher = None
        self.owner = None
        self.autocatcher_enabled = False
        self.lock = asyncio.Lock(loop=self.loop)
        self.verified = True
        self.update_configs()
        # Classes
        self.logger = CustomLogger(self.error_log_path)
        self.stats = StatsMonitor(self)
        self.database = DBConnector(self.pokedb_path)
        self.database.create_caught_table()
        # Commands
        self.task_tracker = TaskTracker(self)
        self.user_changed = {}
        for module in os.listdir("scripts/commands"):
            if module.endswith("commands.py"):
                module_type = module.split("commands.py")[0]
                self.load_commands(module_type)

    def update_configs(self):
        """
        Get the latest configs loaded into the running bot.
        """
        with open(self.config_path, encoding='utf-8') as cfg_file:
            self.configs = json.load(cfg_file)
        self.autocatcher_enabled = self.configs["autocatcher"]
        self.autolog = self.configs["autolog"]
        self.guild_mode = self.configs["default_guildmode"]
        self.channel_mode = self.configs["default_channelmode"]
        self.owner_id = int(self.configs['owner_id'])
        self.prefix = self.configs['command_prefix']
        self.priority_only = self.configs["priority_only"]

    def load_commands(
        self, module_type: str,
        reload_module: bool = False
    ):
        """
        Import all the command modules.
        If reload_module=True, existing module will be reloaded.
        """
        if reload_module:
            module = importlib.reload(
                sys.modules.get(f"scripts.commands.{module_type}commands")
            )
        else:
            module = importlib.import_module(
                f"scripts.commands.{module_type}commands"
            )
        cmd_class = getattr(module, f"{module_type.title()}Commands")
        cmd_obj = cmd_class(ctx=self, database=self.database, logger=self.logger)
        setattr(self, f"{module_type}commands", cmd_obj)
        if module_type == "advanced":
            self.advanced = True
        return cmd_obj

    # Selfbot Base
    async def on_message(self, message: discord.Message):
        """
        The on_message event for Discord API.
        """
        message.__class__ = OverriddenMessage
        id_list = [self.user.id, self.owner_id]
        if self.advanced:
            id_list.extend(self.configs["allowed_users"])
        if (
            message.author.id not in (
                id_list + [self.configs["clone_id"]]
            )
            # DMChannels can complicate the code logic
            or message.guild is None
            # Guild and Channel Checks
            or self.__bl_wl_check(message)
        ):
            return

        # Captcha Lock
        if any([
            all([
                self.stats.total("catches") >= random.randint(995, 999),
                (
                    datetime.now() - self.start_time
                ).total_seconds() < (24 * 60 * 60)
            ]),
            all(
                phrase in message.content
                for phrase in ["Whoa there", str(self.user.id)]
            )
        ]):
            if "Whoa there" in message.content:
                await self.owner.send(
                    f"[{datetime.now().strftime('%x')}] Hey {self.owner.name}, "
                    "please solve my captcha:\n"
                    f"{re.findall(r'(https://.+)', message.content)[0]}"
                )
            self.loop.create_task(self.__captcha_lock())

        # AutoCatcher
        if self.autocatcher_enabled:
            # In case it is enabled through toggle command
            if not self.catcher:
                catcher_module = importlib.import_module(
                    "scripts.base.autocatcher"
                )
                catcher = getattr(catcher_module, "Autocatcher")
                self.catcher = catcher(self, self.database, self.logger)
            await self.catcher.monitor(message)

        # Controller
        prefix_checks = [
            message.content.lower().startswith(
                self.prefix.lower()
            ),
            message.author.id in id_list
        ]
        if all(prefix_checks):
            await self.__handle_cmds(message)

    # Connectors

    # pylint: disable=arguments-differ
    def run(self):
        super().run(self.configs['token'])

    async def on_ready(self):
        """
        The on_ready event for Discord API.
        """
        if not getattr(self, "owner", False):
            self.owner = self.get_user(self.owner_id)
        headers = get_rand_headers()
        self.sess = aiohttp.ClientSession(loop=self.loop, headers=headers)
        if self.autocatcher_enabled:
            catcher_module = importlib.import_module("scripts.base.autocatcher")
            catcher = getattr(catcher_module, "Autocatcher")
            with contextlib.suppress(ModuleNotFoundError):
                customcommands = importlib.import_module(
                    "scripts.commands.customcommands"
                )
                catcher = getattr(customcommands, "Autocatcher", catcher)
            self.catcher = catcher(self, self.database, self.logger)
            self.loop.create_task(self.stats.checkpointer())
        self.ready = True
        if "sleep_handler" not in [
            task._coro.__name__
            for task in asyncio.all_tasks()
        ]:
            self.loop.create_task(sleep_handler(self))
        self.__pprinter()
        await check_for_updates(self)

    # region Private Functions

    def __bl_wl_check(self, message: discord.Message):
        """
        Perform checks for channel and guild whitelisting.
        """
        blacklist_checks = [
            self.channel_mode == "blacklist",
            message.channel.id in self.configs["blacklist_channels"]
        ]
        whitelist_checks = [
            self.channel_mode == "whitelist",
            message.channel.id not in self.configs["whitelist_channels"]
        ]
        blackguild_checks = [
            self.guild_mode == "blacklist",
            message.guild.id in self.configs["blacklist_guilds"]
        ]
        whiteguild_checks = [
            self.guild_mode == "whitelist",
            message.guild.id not in self.configs["whitelist_guilds"]
        ]
        return_checks = [
            all(blacklist_checks),
            all(whitelist_checks),
            all(blackguild_checks),
            all(whiteguild_checks)
        ]
        return any(return_checks)

    async def __captcha_lock(self):
        """
        Toggles the autocatcher and spammer off for 24hrs.
        This is required for captcha circumvention.
        """
        async def sleeper():
            for _ in range(24 * 60 * 60):
                if self.verified:
                    return
                await asyncio.sleep(1)
            self.logger.pprint(
                "It's been a day since the captcha message.\n"
                "Resuming the previous state now.\n"
                "Note: Stats have been reset as well.",
                color="green",
                timestamp=True
            )
        alw_spm = self.allow_spam
        ac_enbl = self.autocatcher_enabled
        coro = None
        was_spamming = [
            task
            for task in asyncio.all_tasks()
            if task._coro.__name__ == "spam"
        ]
        if was_spamming:
            coro = SnoozeSpam(self).get_coro(was_spamming[0])
        self.allow_spam = False
        self.autocatcher_enabled = False
        self.logger.pprint(
            "Caught around 990 pokemons till now.\n"
            "Autocatcher and spammer will be disabled for 24 hrs.\n"
            "This is necessary for bypassing captchas.",
            color="yellow",
            timestamp=True
        )
        self.verified = False
        await sleeper()
        self.stats = StatsMonitor(self)
        self.start_time = datetime.now()
        self.allow_spam = alw_spm
        self.autocatcher_enabled = ac_enbl
        if coro:
            self.loop.create_task(coro)

    def __get_method(self, message: discord.Message):
        """
        Parses the message into command, args, kwargs, etc.
        """
        cleaned_content = message.clean_content
        for user in message.mentions:
            cleaned_content = cleaned_content.replace(
                f" @{user.name}", ""
            )
            if hasattr(user, "nick"):
                cleaned_content = cleaned_content.replace(
                    f" @{user.nick}", ""
                )
        parsed = parse_command(
            self.prefix.lower(),
            cleaned_content.lower()
        )
        cmd = f'cmd_{parsed["Command"]}'
        args = parsed["Args"]
        option_dict = parsed["Kwargs"]
        method = None
        for com in [
            getattr(self, comtype)
            for comtype in sorted(
                dir(self),
                key=lambda x:x.startswith("custom"),
                reverse=True
            )
            if all([
                comtype.endswith('commands'),
                comtype != "load_commands"
            ])
        ]:
            if com.enabled:
                method = getattr(com, cmd, None)
                if method:
                    return method, cmd, args, option_dict
        return method, cmd, args, option_dict

    def __pprinter(self):
        priorities = self.configs['priority']
        prio_list = '\n\t'.join(
            ', '.join(priorities[i:i + 5])
            for i in range(0, len(priorities), 5)
        )
        pretty = {
            itbl: prettify_discord(
                self,
                **{
                    "iterable": self.configs[itbl],
                    "mode": itbl.split("_")[1].rstrip("s")
                }
            )
            for itbl in [
                "blacklist_channels", "whitelist_channels",
                "blacklist_guilds", "whitelist_guilds"
            ]
        }
        ver_ascii = get_ascii(self.version)
        self.logger.pprint(
            '''
                    ██████╗  █████╗ ██╗  ██╗███████╗██████╗  █████╗ ██╗     ██╗
                    ██╔══██╗██╔══██╗██║ ██╔╝██╔════╝██╔══██╗██╔══██╗██║     ██║
                    ██████╔╝██║  ██║█████═╝ █████╗  ██████╦╝███████║██║     ██║
                    ██╔═══╝ ██║  ██║██╔═██╗ ██╔══╝  ██╔══██╗██╔══██║██║     ██║
                    ██║     ╚█████╔╝██║ ╚██╗███████╗██████╦╝██║  ██║███████╗███████╗
                    ╚═╝      ╚════╝ ╚═╝  ╚═╝╚══════╝╚═════╝ ╚═╝  ╚═╝╚══════╝╚══════╝
            ''',
            color=["yellow", "bold"],
            timestamp=False
        )
        self.logger.pprint(
            '''
                    ██████╗ ███████╗██╗     ███████╗██████╗  █████╗ ████████╗
                    ██╔════╝██╔════╝██║     ██╔════╝██╔══██╗██╔══██╗╚══██╔══╝
                    ╚█████╗ █████╗  ██║     █████╗  ██████╦╝██║  ██║   ██║
                    ╚═══██╗ ██╔══╝  ██║     ██╔══╝  ██╔══██╗██║  ██║   ██║
                    ██████╔╝███████╗███████╗██║     ██████╦╝╚█████╔╝   ██║
                    ╚═════╝ ╚══════╝╚══════╝╚═╝     ╚═════╝  ╚════╝    ╚═╝
            ''',
            color=["red"],
            timestamp=False
        )
        self.logger.pprint(
            f"\n{ver_ascii}\n",
            color=["green", "bold"],
            timestamp=False
        )
        print(
            f"\t{self.logger.wrap('Owner:', color='blue')} "
            f"{self.owner} ({self.owner_id})\n\n"
            f"\t{self.logger.wrap('Bot Name:', color='blue')} {self.user}\n\n"
            f"\t{self.logger.wrap('Command Prefix:', color='blue')} "
            f"{self.configs['command_prefix']}\n\n"
            f"\t{self.logger.wrap('Catching For:', color='blue')} "
            f"{self.get_user(int(self.configs['clone_id']))} "
            "(Might be None but no problemo)\n\n"
            f"\t{self.logger.wrap('Priority List', color='blue')}\n"
            "\t~~~~~~~~~~~~~\n"
            f"\t{prio_list}\n\n"
            f"\t{self.logger.wrap('Catch Rate:', color='blue')} "
            f"{self.configs['catch_rate']}%\n\n"
            f"\t{self.logger.wrap('Catch Delay:', color='blue')} "
            f"{self.configs['delay']} seconds\n\n"
            f"\t{self.logger.wrap('Delay on Priority:', color='blue')} "
            f"{'On' if self.configs['delay_on_priority'] else 'Off'}\n\n"
            f"\t{self.logger.wrap('Restrict Duplicates Catching:', color='blue')} "
            f"{'On' if self.configs['restrict_duplicates'] else 'Off'}\n\n"
            f"\t{self.logger.wrap('Max Duplicates:', color='blue')} "
            f"{self.configs['max_duplicates']}\n\n"
            f"\t{self.logger.wrap('Blacklisted Channels', color='blue')}\n"
            "\t~~~~~~~~~~~~~~~~~~~~\n"
            f"\t{pretty['blacklist_channels']}\n\n"
            f"\t{self.logger.wrap('Whitelisted Channels', color='blue')}\n"
            "\t~~~~~~~~~~~~~~~~~~~~\n"
            f"\t{pretty['whitelist_channels']}\n\n"
            f"\t{self.logger.wrap('Blacklisted Servers', color='blue')}\n"
            "\t~~~~~~~~~~~~~~~~~~~\n"
            f"\t{pretty['blacklist_guilds']}\n\n"
            f"\t{self.logger.wrap('Whitelisted Servers', color='blue')}\n"
            "\t~~~~~~~~~~~~~~~~~~~\n"
            f"\t{pretty['whitelist_guilds']}\n\n"
            f"\t{self.logger.wrap('Default Channel Mode:', color='blue')} "
            f"{self.configs['default_channelmode']}\n\n"
            f"\t{self.logger.wrap('Default Guild Mode:', color='blue')} "
            f"{self.configs['default_guildmode']}\n\n"
            f"\t{self.logger.wrap('Log Level:', color='blue')} "
            f"{self.configs['log_level']}\n\n"
            f"\t{self.logger.wrap('Autocatcher:', color='blue')} "
            f"{'On' if self.configs['autocatcher'] else 'Off'}\n\n"
            f"\t{self.logger.wrap('Priority Only:', color='blue')} "
            f"{'On' if self.configs['priority_only'] else 'Off'}\n\n"
            f"\t{self.logger.wrap('IV Threshold:', color='blue')} "
            f"{self.configs['iv_threshold']}%\n\n"
            f"\t{self.logger.wrap('Typo Rate:', color='blue')} "
            f"{self.configs['typo_rate']}%\n\n"
            f"\t{self.logger.wrap('Autosleep:', color='blue')} "
            f"{'On' if self.configs['autosleep'] else 'Off'}\n\n"
            f"\t{self.logger.wrap('Exploit p!hint:', color='blue')} "
            f"{'On' if self.configs.get('exploit_hint', False) else 'Off'}\n\n"
            f"\t{self.logger.wrap('Confidence Threshold:', color='blue')} "
            f"{self.configs['confidence_threshold']}%\n\n"
        )
        if self.configs['autosleep']:
            print(
                f"\t{self.logger.wrap('Stay Awake Time:', color='blue')} "
                f"{get_formatted_time(int(self.configs['inter_sleep_delay']))}\n\n"
                f"\t{self.logger.wrap('Autosleep Time:', color='blue')} "
                f"{get_formatted_time(int(self.configs['sleep_duration']))}\n\n"
            )
        if self.advanced:
            allowed_users = '\n\t'.join(
                f"{self.get_user(user_id)} ({user_id})"
                for user_id in self.configs['allowed_users']
            )
            alts = ', '.join(self.configs['alts'])
            print(
                f"\t{self.logger.wrap('Allowed Users', color='blue')}\n"
                "\t~~~~~~~~~~~~~~\n"
                f"\t{allowed_users}\n\n"
                f"\t{self.logger.wrap('Prefixes of Alts', color='blue')}\n"
                "\t~~~~~~~~~~~~~~~~\n"
                f"\t{alts}\n\n"
            )
        self.logger.pprint(
            "▲▲▲▲▲ Pssst. You might wanna scroll up "
            "if you've never done it before. ▲▲▲▲▲",
            color="yellow"
        )

    async def __handle_cmds(self, message):
        with contextlib.suppress(discord.Forbidden):
            await message.delete()
        res = self.__get_method(message)
        method, cmd, args, option_dict = res
        if not method:
            # Not a selfbot command,
            # so execute it as a Poketwo command.
            cmd = cmd.replace('cmd_', '')
            args.insert(0, cmd)
            method = getattr(self.pokecommands, "cmd_poke_exec")
        kwargs = {
            "message": message,
            "args": args,
            "mentions": message.mentions or [],
            **option_dict
        }
        try:
            task = method(**kwargs)
            # Decorators return None
            if task:
                await task
        except Exception:  # pylint: disable=broad-except
            tb_obj = traceback.format_exc()
            self.logger.pprint(
                tb_obj,
                timestamp=True,
                color="red"
            )

    # endregion
