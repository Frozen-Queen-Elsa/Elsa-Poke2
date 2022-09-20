"""
Compilation of command decorators and the Base class for Commands.
"""

# pylint: disable=unused-argument

from __future__ import annotations
from abc import ABC
from functools import wraps
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pokeball import PokeBall


def get_prefix(func: Callable):
    '''
    Get poketwo's mention as a prefix.
    '''
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        pref = f'<@{self.ctx.configs["clone_id"]}> '
        kwargs['pref'] = pref
        return func(self, *args, message=message, **kwargs)
    return wrapped


def paginated(func: Callable):
    '''
    Warns the user to login from owner account for commands
    that are paginated with reactions.
    '''
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if self.ctx.user.id != message.author.id:
            return func(self, *args, message=message, **kwargs)
        self.logger.pprint(
            'You need to use this command while logged in as the owner account.',
            color="red",
            wrapped_func=func.__name__
        )
        return None
    return wrapped


def soft_paginated(func: Callable):
    '''
    An exception case for the Help command which has dual functionality.
    Pagination is not required for a specific command's help message.
    '''
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if any([
            self.ctx.user.id != message.author.id,
            len(kwargs["args"]) > 0
        ]):
            return func(self, *args, message=message, **kwargs)
        self.logger.pprint(
            'You need to use this command while logged in as the owner account.',
            color="red",
            wrapped_func=func.__name__
        )
        return None
    return wrapped


def check_db(func: Callable):
    '''
    Can be used to check if no pokemons have been logged.
    Simply prints and logs the error if total logged pokemons is zero.
    '''
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        if (
            self.database.get_total() != 0
            or all([
                all(arg.isdigit() for arg in args),
                func.__name__ == "cmd_trade"
            ])
            or all([
                func.__name__ == 'cmd_autofav',
                len(kwargs) > 1
            ])
        ):
            return func(self, *args, message=message, **kwargs)
        self.logger.pprint(
            "Looks like your pokelog is empty.\n"
            f"Use {self.ctx.prefix}pokelog before using this command.",
            timestamp=True,
            color="red"
        )
        return None
    return wrapped


def get_chan(func: Callable):
    '''
    Gets the active channel if there's one present, else returns the message channel.
    '''
    @wraps(func)
    def wrapped(self, message, *args, **kwargs):
        chan = kwargs.get(
            "channel",
            kwargs.get(
                "chan",
                (
                    self.ctx.active_channels[-1]
                    if self.ctx.active_channels
                    else message.channel
                )
            )
        )
        kwargs.update({'chan': chan})
        return func(self, *args, message=message, **kwargs)
    return wrapped


def maintenance(text: Optional[str] = None):
    '''
    Disable a broken/wip function to prevent it from affecting rest of the selfbot.
    '''
    def decorator(func: Callable):
        func.__dict__["disabled"] = True
        func.__dict__["disabled_text"] = text

        @wraps(func)
        def wrapped(self, message, *args, **kwargs):
            text = func.__dict__.get("disabled_text", None)
            if text is None:
                func_name = func.__name__.replace('cmd_', '')
                text = self.logger.pprint(
                    f"The command {func_name} is under maintenance.\n"
                    "Wait for a future update to see changes.",
                    timestamp=True,
                    color="red"
                )
            self.logger.pprint(text, timestamp=True, color="red")
        return wrapped
    return decorator


class Commands(ABC):
    '''
    The Root/Base command class which serves as the starting point for all commands.
    Can be used to enable/disable entire categories which might come in handy later.
    '''
    def __init__(self, ctx: PokeBall, *args, **kwargs):
        self.ctx = ctx
        self.database = self.ctx.database
        self.logger = self.ctx.logger
        self.enabled = kwargs.get('enabled', True)

    @property
    def enable(self):
        '''
        Making it a property let's us use it as both a function and as an attribute.
        Commands().enable() and Commands().enable are equivalent.
        '''
        self.enabled = True
        return self.enabled

    @property
    def disable(self):
        '''
        Making it a property let's us use it as both a function and as an attribute.
        Commands().disable() and Commands().disable are equivalent.
        '''
        self.enabled = False
        return self.enabled
