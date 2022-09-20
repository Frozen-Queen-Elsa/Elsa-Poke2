"""
Different types of message checks.
"""

# pylint: disable=inconsistent-return-statements, too-many-arguments

from __future__ import annotations
import random
import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pokeball import PokeBall
    from discord import (
        Message, TextChannel,
        Member, Reaction
    )


def poketwo_reply_ac(msg: Message, ctx: PokeBall):
    """ Normal Poketwo message check for autocatcher. """
    if msg.author.id == ctx.configs["clone_id"]:
        return True


def poketwo_embed_ac(msg: Message, ctx: PokeBall):
    """ Embed Poketwo message check for autocatcher. """
    if poketwo_reply_ac(msg, ctx) and len(msg.embeds) > 0:
        return True


def poketwo_hint(
    msg: Message,
    ctx: PokeBall,
    message: Message
):
    """ Pokemon hint message check. """
    if poketwo_reply_cmd(
        msg, ctx, message
    ) and msg.content.startswith(
        'The pokémon is'
    ):
        return True


def spawn_checks(msg: Message, ctx: PokeBall):
    """ Pokemon Spawn embed message check. """
    if poketwo_embed_ac(
        msg, ctx
    ) and "wild" in msg.embeds[0].title:
        return True


def is_ranked(name: str, ctx: PokeBall):
    """ Check if pokemon is legendary/UB/alolan/etc. """
    if name.title() in ctx.legendaries:
        return True


def is_priority(name: str, ctx: PokeBall):
    """ Check if pokemon is in priority list. """
    if name.title() in [
        poke.title()
        for poke in ctx.configs['priority']
    ]:
        return True


def priority_checks(name: str, ctx: PokeBall):
    """ Check if pokemon is ranked or priority. """
    checks = [
        is_ranked(name, ctx),
        is_priority(name, ctx)
    ]
    if any(checks):
        return True


def duplicate_checks(name: str, ctx: PokeBall):
    """ Check if pokemon is a duplicate. """
    checks = [
        not priority_checks(name, ctx),
        ctx.configs["restrict_duplicates"],
        ctx.database.get_total(name=name) > ctx.configs["max_duplicates"]
    ]
    if all(checks):
        return True


def catch_checks(name: str, ctx: PokeBall):
    """ Check if the pokemon should be catched. """
    if ctx.priority_only and priority_checks(name, ctx):
        return True
    if priority_checks(name, ctx):
        return True

    catch_subchecks = [
        random.randint(1, 100) <= ctx.configs['catch_rate'],
        not ctx.sleep,
        name.lower() not in [
            poke.lower()
            for poke in ctx.configs['avoid']
        ],
        not ctx.priority_only
    ]
    if all(catch_subchecks):
        if not duplicate_checks(name, ctx):
            return True
        ctx.logger.pprint(
            f"Skipping the duplicate: {name}",
            timestamp=True,
            color="blue"
        )
        ctx.catching = False


def delay_checks(name: str, ctx: PokeBall):
    """ Check if delay is required before autocatching. """
    checks = [
        all([
            ctx.configs['delay_on_priority'],
            priority_checks(name, ctx)
        ]),
        not priority_checks(name, ctx)
    ]
    if any(checks):
        return True


def already_caught(
    msg: Message, ctx: PokeBall,
    message: Message, name: str
):
    """ Check if someone sniped pokemon before you. """
    if poketwo_reply_cmd(msg, ctx, message) and all(
        word in msg.content.lower()
        for word in [name, "congratulations", "caught"]
    ):
        return True


def poketwo_reply_cmd(
    msg: Message, ctx: PokeBall,
    message: Message,
    chan: Optional[TextChannel] = None,
    contains: Optional[str] = None
):
    """ Normal Poketwo message check for commands. """
    if not chan:
        chan = message.channel
    checks = [
        msg.author.id == ctx.configs["clone_id"],
        msg.channel.id == chan.id
    ]
    if contains:
        if isinstance(contains, list):
            checks.append(
                all(
                    re.sub(
                        r'[^\x00-\x7f]',
                        '',
                        word
                    ).strip().lower() in msg.content.lower()
                    for word in contains
                )
            )
        elif isinstance(contains, set):
            checks.append(
                any(
                    re.sub(
                        r'[^\x00-\x7f]',
                        '',
                        word
                    ).strip().lower() in msg.content.lower()
                    for word in contains
                )
            )
        else:  # String
            contains = re.sub(r'[^\x00-\x7f]', '', contains).strip()
            checks.append(
                contains.lower() in msg.content.lower()
            )
    if all(checks):
        return True


def poketwo_embed_cmd(
    msg: Message, ctx: PokeBall,
    message: Message,
    chan: Optional[TextChannel] = None,
    title_contains: Optional[str] = None,
    description_contains: Optional[str] = None,
    footer_contains: Optional[str] = None,
    fields_contains: Optional[str] = None
):
    """ Embed Poketwo message check for commands. """
    if not chan:
        chan = message.channel
    if poketwo_reply_cmd(
        msg, ctx, message, chan=chan
    ) and len(msg.embeds) > 0:
        checks = []
        for emb in msg.embeds:
            if title_contains:
                checks.append(
                    title_contains.lower() in emb.title.lower()
                )
            if description_contains:
                checks.append(
                    description_contains.lower() in emb.description.lower()
                )
            if footer_contains:
                checks.append(
                    footer_contains.lower() in emb.footer.text.lower()
                )
            if fields_contains:
                checks.append(
                    fields_contains.lower()
                    in " ".join(field.value for field in emb.fields)
                )
            if all(checks):
                return True


def user_check(
    msg: Message, message: Message,
    chan: Optional[TextChannel] = None
):
    """ User message check. """
    if not chan:
        chan = message.channel
    checks = [
        msg.channel.id == chan.id,
        msg.author.id == message.author.id,
    ]
    if all(checks):
        return True


def user_rctn(
    message: Message, user: Member,
    rctn: Reaction, usr: Member,
    chan: Optional[TextChannel] = None,
    contains: Optional[str] = None
):
    """ User reaction check. """
    if not chan:
        chan = message.channel
    checks = [
        usr.id == user.id,
        rctn.message.channel.id == chan.id
    ]
    if contains:
        checks.append(
            contains.lower() in rctn.message.content.lower()
        )
    if all(checks):
        return True
