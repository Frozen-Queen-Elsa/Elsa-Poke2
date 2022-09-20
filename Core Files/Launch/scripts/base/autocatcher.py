"""
Autocatcher - The core feature of PokeBall SelfBot
"""


# pylint: disable=too-many-instance-attributes, too-few-public-methods
# pylint: disable=too-many-locals, too-many-arguments, unused-argument

from __future__ import annotations
import asyncio
import contextlib
import random
import re
import traceback
from datetime import datetime
from typing import Tuple, TYPE_CHECKING, Union

import discord

from ..helpers.checks import (
    already_caught, catch_checks, delay_checks,
    duplicate_checks, is_priority, poketwo_embed_cmd,
    poketwo_hint, poketwo_reply_cmd, priority_checks,
    spawn_checks
)
from ..helpers.utils import get_embed, log_formatter, send_embed, typowrite, wait_for
from .pokedetector import PokeDetector

if TYPE_CHECKING:
    from pokeball import PokeBall


class Autocatcher:
    """The Autocatcher module for Pokeball Selfbot.

    This class is an interface that connects:
        1. Prediction
        2. Handling Fake Typo
        3. Logging to Database
        4. Sending DM logs to Owner account

    Attributes
    ----------
    ctx : Pokeball
        the root class for the Selfbot.
    database : DbConnector
        the class which handles local Database connections.
    logger : CustomLogger
        the custom logger class.

    Methods
    -------
    get_formatted_name(caught_msg, name)
        Simply adds the pokemon name inside Square brackets
        and appends Shiny inside if required.

    generate_log_embed(message, *pokemon_details, poketype, embed_color)
        Creates an appropriate Embed which can be DMed to the owner.

    lock_channel(channel)
        Ignores a channel if the selfbot account can't send the catch message in it.

    [async] exploit_hint(message, incorrect_name)
        In case of an incorrect prediction,
        we can exploit the p!hint system to get the correct name.

    [async] let_others_catch(message, name)
        Wait for configured delay in time before catching, giving others a chance.

    [async] handle_logging(message, caught_reply, name)
        Handles the conditional logging based on the configured log_level.

    [async] monitor(message)
        The main function which patches the autocatcher onto the selfbot.
    """
    def __init__(self, ctx: PokeBall, *args, **kwargs):
        self.ctx = ctx
        self.pref = f'<@{int(self.ctx.configs["clone_id"])}> '
        self.detector = PokeDetector(
            classes_path=self.ctx.pokeclasses_path,
            model_path=self.ctx.pokemodel_path,
            session=self.ctx.sess
        )
        self.database = self.ctx.database
        self.logger = self.ctx.logger
        self.locked_channels = []
        self.caught_pokemons = 0
        self.poketypes = {
            "Common": 9807270,
            "Priority": 3066993,
            "Legendary": 15728640,
            "Mythical": 15728640,
            "Ultrabeast": 15728640,
            "Forms": 15728640,
            "Shiny": 16045597
        }
        self.warn_no_owner = True
        self.warn_no_recatch = True
        self.warn_no_autolog = True

    @staticmethod
    def _get_formatted_name(caught_msg: discord.Message, name: str) -> str:
        return f"[Shiny {name}]" if any([
            all([
                "shiny" in caught_msg,
                "chain" not in caught_msg
            ]),
            "unusual" in caught_msg
        ]) else f"[{name}]"

    def _generate_log_embed(
        self, message: discord.Message,
        name: str, level: int, total_iv: float,
        poketype: str, color: int
    ) -> discord.Embed:
        catchphrase = get_embed(
            title=f"Caught a poke! [{self.caught_pokemons}]",
            content=f"**{name.title()}**",
            color=color,
            url=message.jump_url
        )
        thumb_url = "https://raw.githubusercontent.com/Hyperclaw79/" + \
            "PokeBall-SelfBot/master/assets/emblem.png"
        catchphrase.set_thumbnail(url=thumb_url)
        catchphrase.add_field(
            name="**Level**",
            value=level,
            inline=False
        )
        catchphrase.add_field(
            name="**Type**",
            value=poketype,
            inline=False
        )
        if total_iv > 0:
            catchphrase.add_field(
                name="**Total IV%**",
                value=total_iv,
                inline=False
            )
        catchphrase.add_field(
            name="**Guild**",
            value=str(message.guild),
            inline=False
        )
        catchphrase.add_field(
            name="**Channel**",
            value=str(message.channel),
            inline=False
        )
        catchphrase.set_footer(
            text=f"Caught on {datetime.now().strftime('%I:%M:%S %p')}."
        )
        if poketype != "Common":
            catchphrase.set_image(url=message.embeds[0].image.url)
        return catchphrase

    def _lock_channel(self, channel: discord.TextChannel):
        self.ctx.catching = False
        if channel in self.locked_channels:
            return
        self.locked_channels.append(channel.id)
        self.logger.pprint(
            f"Unable to catch pokemons in {channel} at {channel.guild}.\n"
            "Missing SEND MESSAGE permissions there.",
            color="red"
        )

    async def _exploit_hint(
        self, message: discord.Message,
        incorrect: str
    ) -> Tuple[discord.Message, str]:
        def check_match(hint, name):
            if len(hint) == len(name):
                return all(
                    name[i].lower() == c.lower()
                    for i, c in enumerate(hint)
                    if c != '_'
                )
            return False

        hint_msg = await message.channel.send(f"{self.pref}hint")
        hint = await wait_for(
            message.channel, self.ctx, init_msg=hint_msg,
            check=lambda msg: poketwo_hint(msg, self.ctx, message),
            timeout=max(0.5, self.ctx.configs["delay"])
        )
        hint = hint.content.split('The pokémon is ')[1]
        hint = hint.replace("\\", '')[:-1]  # Last character is a '.'
        namelist = [
            _
            for _ in (
                [
                    poke.title()
                    for poke in self.ctx.pokenames
                ] + self.ctx.legendaries + ["Flabébé"]
            )
            if check_match(hint, _)
        ]
        if not namelist:
            self.logger.pprint(
                f"Unknown Pokemon {hint.title()} was wrongly predicted "
                f"as {incorrect}.\n"
                "Most likely a new pokemon not in the pokeclasses list.",
                timestamp=True,
                color="red"
            )
            return (None, None)
        correct = namelist[0]
        catch_msg = await message.channel.send(f"{self.pref}c {correct}")
        try:
            caught_reply = await wait_for(
                message.channel, self.ctx,
                init_msg=catch_msg,
                check=lambda msg: poketwo_reply_cmd(
                    msg, self.ctx, message,
                    contains={"caught", "wrong"}
                ),
                timeout=max(0.5, self.ctx.configs["delay"])
            )
            self.logger.pprint(
                f"{correct} was wrongly predicted as {incorrect}.",
                timestamp=True,
                color="red"
            )
            return caught_reply, correct
        except asyncio.TimeoutError:
            return None, None

    async def _autolog(
        self, message: discord.Message,
        caught_reply: discord.Message,
        name: str, level: int
    ):
        total_iv = 0
        if self.ctx.autolog:
            await asyncio.sleep(random.uniform(2.0, 2.5))
            async with message.channel.typing():
                pp_msg = await message.channel.send(
                    f"{self.pref}pokemon --name {name} --level {level}"
                )
            with contextlib.suppress(asyncio.TimeoutError):
                reply = await wait_for(
                    message.channel, self.ctx, init_msg=pp_msg,
                    check=lambda msg: poketwo_embed_cmd(
                        msg, self.ctx, message,
                        title_contains="Your pokémon"
                    ), timeout=max(0.5, self.ctx.configs["delay"])
                )
                raw_list = reply.embeds[0].description.splitlines()
                refined_list = [
                    log_formatter(self.ctx, pokeline)
                    for pokeline in raw_list
                    if not self.database.assert_pokeid(
                        log_formatter(self.ctx, pokeline)["pokeid"]
                    )
                ]
                latest = sorted(refined_list, key=lambda x: x["pokeid"])[-1]
                latest.update({
                    "caught_on": caught_reply.created_at.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                })
                total_iv = latest["iv"]
                self.database.insert_caught(**latest)
        elif self.warn_no_autolog:
            self.logger.pprint(
                "Autolog is disabled by default as it's a risky option.\n"
                "If you want to enable it, set autolog to true in the configs.",
                timestamp=False,
                color="yellow"
            )
            self.warn_no_autolog = False
        return total_iv

    async def _dm_log(
        self, message: discord.Message,
        name: str, level: int, total_iv: float,
        name_str: str
    ):
        poketype = [
            pt.title()
            for pt, names in self.ctx.pokeranks.items()
            if name.title() in names
        ]
        if poketype:
            poketype = poketype[0]
        elif is_priority(name, ctx=self.ctx):
            poketype = "Priority"
        elif "Shiny" in name_str:
            poketype = "Shiny"
        else:
            poketype = "Common"
        color = self.poketypes[poketype]
        log_embed = self._generate_log_embed(
            message, name, level,
            total_iv, poketype, color
        )
        if not self.ctx.owner:
            results = await message.guild.query_members(
                user_ids=[self.ctx.owner_id]
            )
            if not results:
                if self.warn_no_owner:
                    self.logger.pprint(
                        f"Unable to find the owner account "
                        f"in the >{message.guild} server.",
                        timestamp=True,
                        color="yellow"
                    )
                    self.warn_no_owner = False
                return
            self.ctx.owner = results[0]
        try:
            prio = None
            if any([
                all([
                    self.ctx.configs["log_level"].title() == "Priority",
                    poketype != "Common"
                ]),
                self.ctx.configs["log_level"].title() == "Default"
            ]):
                prio = await send_embed(self.ctx.owner, embed=log_embed)
            if poketype != "Common" and prio:
                with contextlib.suppress(discord.Forbidden, discord.HTTPException):
                    await prio.pin()
        except AttributeError:
            if self.ctx.user.id == self.ctx.owner_id:
                self.logger.pprint(
                    "Looks like you're using the bot account's ID as owner_id "
                    "which should belong to an alt account.\n"
                    "Please change it in the configs and restart the bot "
                    "to supress this message and enable DM logging.",
                    color="red"
                )
                return
            self.logger.pprint(
                "Unable to find the Owner for the bot. "
                "Make sure both the accounts are friends on Discord.",
                color="red"
            )

    async def _handle_logging(
        self, message: discord.Message,
        caught_reply: discord.Message,
        name: str
    ):
        level = re.findall(r"level\s(\d+)\s", caught_reply.content)[0]
        total_iv = 0
        name_str = self._get_formatted_name(caught_reply.content, name)
        if self.ctx.configs["log_level"].title() != "Silent":
            self.logger.pprint(
                f"Caught a level {level} {name_str.title()} "
                f"in #{message.channel} at >{message.guild}.",
                timestamp=True,
                color="green"
            )
        total_iv = await self._autolog(
            message, caught_reply,
            name, level
        )
        return (
            await self._dm_log(
                message, name, level,
                total_iv, name_str
            )
        )

    async def _handle_wrong(
        self, message: discord.Message,
        name: str, confidence: float
    ):
        if self.ctx.configs.get("exploit_hint", False):
            caught_reply, name = await self._exploit_hint(message, name)
            if not caught_reply:
                self.logger.pprint(
                    "Unable to catch the spawned pokemon.\n"
                    "Might be fixed in the next update.",
                    timestamp=True,
                    color="red"
                )
                return
            return caught_reply, name
        self.logger.pprint(
            f"{name.title()} was wrongly predicted "
            f"(with {confidence * 100:2.2f}% confidence).\n"
            "Skipping hint exploitation based on configs.",
            timestamp=True,
            color="red"
        )
        if self.warn_no_recatch:
            self.logger.pprint(
                "Exploiting Hint is disabled by default as it's a risky option.\n"
                "If you want to enable it, set exploit_hint to true in the configs.",
                timestamp=False,
                color="yellow"
            )
            self.warn_no_recatch = False
        return

    async def _let_others_catch(
        self, message: discord.Message,
        name: str
    ) -> Union[bool, None]:
        delay_time = self.ctx.configs['delay'] + min(
            max(0, random.gauss(0, 0.3)),
            0.2
        )
        gone = await wait_for(
            message.channel, self.ctx,
            check=lambda msg: already_caught(msg, self.ctx, message, name),
            timeout=delay_time
        )
        if gone:
            self.logger.pprint(
                f"{name.title()} claimed by {gone.mentions[0]}.",
                timestamp=True,
                color="red"
            )
            self.ctx.catching = False
            return True

    async def _precatch(
        self, message: discord.Message
    ) -> Union[tuple, None]:
        if not spawn_checks(message, ctx=self.ctx):
            return None
        self.ctx.catching = True
        url = message.embeds[0].image.url
        img_path = await self.detector.get_image_path(url)
        name, confidence = self.detector.predict(img_path)
        name = name.title()
        if any([
            not self.ctx.sleep,
            all([
                self.ctx.sleep,
                priority_checks(name, self.ctx)
            ])
        ]):
            self.ctx.stats.update_spawns(name)
        if all([
            confidence < self.ctx.configs.get("confidence_threshold", 25) / 100,
            not priority_checks(name, self.ctx)
        ]):
            self.logger.pprint(
                f"Confidence score for the spawned {name} "
                f"is very low ({confidence * 100:2.2f}%), so skipping it!",
                timestamp=True,
                color="yellow"
            )
            return None
        self.logger.pprint(
            f"A {name} ({confidence * 100:2.2f}% confident) spawned "
            f"on the channel {message.channel} in server {message.guild}.",
            timestamp=True,
            color="blue"
        )
        return url, name, confidence

    async def _catch(
        self, message: discord.Message,
        name: str
    ) -> Union[discord.Message, None]:
        typo_rate = int(self.ctx.configs.get("typo_rate", 0))
        name2 = name.lower() if not typo_rate else typowrite(name, typo_rate)
        if delay_checks(name, ctx=self.ctx):
            too_late = await self._let_others_catch(message, name)
            if too_late:
                return None
        name = name.lower()
        if name2 != name:
            if self.ctx.configs["delay"] > 0:
                async with message.channel.typing():
                    catch_msg = await message.channel.send(f"{self.pref}c {name2}")
            else:
                catch_msg = await message.channel.send(f"{self.pref}c {name2}")
            await asyncio.sleep(random.uniform(0.5, 1.0))
        if self.ctx.configs["delay"] > 0:
            async with message.channel.typing():
                catch_msg = await message.channel.send(f"{self.pref}c {name}")
        else:
            catch_msg = await message.channel.send(f"{self.pref}c {name}")
        caught_reply = await wait_for(
            message.channel, self.ctx, 'message', init_msg=catch_msg,
            check=lambda msg: poketwo_reply_cmd(
                msg, self.ctx, message,
                contains={"wrong", "caught"}
            ),
            timeout=max(0.5, self.ctx.configs["delay"])
        )
        if not caught_reply:
            self.logger.pprint(
                f"Unable to read the reply for the catch message.\n"
                f"Logging will be skipped for {name}.",
                timestamp=True,
                color="yellow"
            )
            return None
        return caught_reply

    async def monitor(self, message: discord.Message):
        """
        The main function which patches the autocatcher onto the selfbot.
        """
        rets = await self._precatch(message)
        if not rets:
            self.ctx.catching = False
            return
        url, name, confidence = rets
        orig_name = name
        if catch_checks(name, ctx=self.ctx):
            try:
                caught_reply = await self._catch(message, name)
                if not caught_reply:
                    self.ctx.catching = False
                    return
                if "wrong" in caught_reply.content:
                    self.ctx.stats.update_misses(name)
                    self.ctx.stats.update_misses_urls(name, url)
                    rets = await self._handle_wrong(message, name, confidence)
                    if not rets:
                        self.ctx.catching = False
                        return
                    caught_reply, name = rets
                elif self.ctx.user.mentioned_in(caught_reply):
                    self.ctx.stats.update_catches(name)
                    self.ctx.stats.update_confidence(name, confidence)
                    self.caught_pokemons += 1
                    await self._handle_logging(message, caught_reply, name)
                self.ctx.catching = False
            except discord.errors.Forbidden:
                self._lock_channel(message.channel)
            except Exception:  # pylint: disable=broad-except
                tb_obj = traceback.format_exc()
                self.logger.pprint(
                    tb_obj,
                    timestamp=True,
                    color="red"
                )
            finally:
                self.ctx.catching = False
        elif all([
            not self.ctx.sleep,
            # Catch_checks will return False for duplicates as well,
            # in which case, we're already logging it.
            not duplicate_checks(orig_name, self.ctx),
            not self.ctx.priority_only
        ]):
            self.ctx.catching = False
            self.logger.pprint(
                f"Skipping {name} randomly based on catch rate.",
                timestamp=True,
                color="blue"
            )
