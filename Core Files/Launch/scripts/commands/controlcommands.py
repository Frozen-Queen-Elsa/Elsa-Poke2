"""
Control Commands Module
"""

# pylint: disable=unused-argument

import os
import subprocess
from typing import List, Optional

from discord import Message

from ..helpers.utils import (
    get_embed, get_enum_embed, send_embed
)
from .basecommand import Commands, maintenance


class ControlCommands(Commands):
    '''
    Commands that either control/interact with other commands or
    provide selfbot specific functionality.
    Examples:
        Togglers, Help, Command Lister,
        Setup_server, Restart, Channel
    '''

    @maintenance
    async def cmd_restart(self, message: Message, **kwargs):
        """Closes session and spawns a new process.
        $```scss
        {command_prefix}restart
        ```$

        @Restarts the bot with local changes.@
        """
        await self.ctx.sess.close()
        await self.ctx.close()
        # Need to implement a way to kill the current process first.
        subprocess.run("python launcher.py", check=False)

    async def cmd_toggle(
        self, message: Message,
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Toggle a boolean property of the Pokeball class.
        $```scss
        {command_prefix}toggle property [on/enable/whitelist]
        {command_prefix}toggle property [off/disable/blacklist]
        ```$

        @Toggle some of the config options dynamically.
        Currently, you can toggle:
            Autocatcher, Autolog, Channel_Mode,
            Guild_Mode, Priority, Spam@

        ~To enable the autologging:
            ```
            {command_prefix}toggle autolog enable
            ```
        To operate in Whitelist Guild mode:
            ```
            {command_prefix}toggle guildmode whitelist
            ```~
        """
        props = {
            "Autocatcher": "autocatcher_enabled",
            "Autolog": "autolog",
            "Autosnipe": "autosnipe",
            "Channel_Mode": "channel_mode",
            "Guild_Mode": "guild_mode",
            "Priority": "priortiy_only",
            "Spam": "allow_spam"
        }
        if not args:
            await send_embed(
                message.channel,
                embed=get_enum_embed(
                    list(props),
                    title="List of Possible Options"
                )
            )
            return
        if len(args) >= 2:
            prop = args[0].title()
            state = args[1].lower()
        elif len(args) == 1:
            prop = args[0].title()
            state = None
        if prop not in list(props):
            await send_embed(
                message.channel,
                embed=get_enum_embed(
                    list(props),
                    title="List of Possible Options"
                )
            )
            return
        bool_toggles = ["enable", "on", "disable", "off"]
        str_toggles = ["whitelist", "blacklist"]
        possible_states = bool_toggles + str_toggles
        if state in bool_toggles:
            state = bool_toggles.index(state) < 2
        elif state in str_toggles:
            if prop not in ["Guild_Mode", "Channel_Mode"]:
                await send_embed(
                    message.channel,
                    embed=get_enum_embed(
                        list(props)[2:4],
                        title="List of Possible Options"
                    )
                )
                return
        elif state is None:
            if getattr(self.ctx, props[prop]) not in ["whitelist", "blacklist"]:
                state = not getattr(self.ctx, props[prop])
            else:
                state = str_toggles[
                    1 - str_toggles.index(
                        getattr(self.ctx, props[prop])
                    )
                ]
        else:
            embed = get_enum_embed(
                possible_states,
                title="Possible toggle states"
            )
            await send_embed(message.channel, embed=embed)
            return
        self.ctx.user_changed.update({
            props[prop]: state
        })
        setattr(self.ctx, props[prop], state)
        await send_embed(
            message.channel,
            embed=get_embed(
                f"Successfully toggled **{prop}** to `{str(state).title()}`."
            )
        )

    async def cmd_toggle_module_state(
        self, message: Message,
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Enable or Disable different command modules.
        $```scss
        {command_prefix}toggle_module_state module_name [on/off]
        ```$

        @For enabling or disabling a commands module.@

        ~To enable the Pokecommands module:
            ```
            {command_prefix}toggle_module_state poke enable
            ```
        To disable the Normalcommands module:
            ```
            {command_prefix}toggle_module_state normal disable
            ```~
        """
        if not args:
            module = ""
            state = "enable"
        elif len(args) >= 2:
            module = args[0].lower()
            state = args[1].lower()
        elif len(args) == 1:
            module = args[0].lower()
            state = "enable"
        possible_states = ["enable", "on", "disable", "off"]
        if state in possible_states:
            enable = possible_states.index(state) < 2
        else:
            embed = get_enum_embed(
                possible_states,
                title="Possible toggle states"
            )
            await send_embed(message.channel, embed=embed)
        possible_modules = [
            cmd.replace("commands", "")
            for cmd in dir(self.ctx)
            if cmd.endswith("commands") and cmd != "load_commands"
        ] + ["config"]
        if module not in possible_modules:
            embed = get_enum_embed(
                possible_modules,
                title="List of toggleable modules"
            )
            await send_embed(message.channel, embed=embed)
        else:
            if module == "advanced":
                if "advancedcommands.py" in os.listdir("."):
                    self.ctx.advancedcommands.enabled = enable
                else:
                    embed = get_embed(
                        "You need to purchase the Advanced Extension first.",
                        embed_type="error"
                    )
                    embed.set_footer(text="Please contact Hyper for details.")
                    await send_embed(message.channel, embed=embed)
            else:
                getattr(self.ctx, f"{module}commands").enabled = enable
            await send_embed(
                message.channel,
                embed=get_embed(
                    f"Successfully switched {module} to {state}."
                )
            )

    async def cmd_reload(
        self, message: Message,
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Hot reload commands or configs.
        $```scss
        {command_prefix}reload module_name
        ```$

        @For hot reloading changes in a commands module/configs.@

        ~To reload changes in Pokecommands:
            ```
            {command_prefix}reload poke
            ```
        To reload changes in Configs:
            ```
            {command_prefix}reload config
            ```~
        """
        if not args:
            return
        module = args[0].lower()
        possible_modules = [
            cmd.replace("commands", "")
            for cmd in dir(self.ctx)
            if cmd.endswith("commands") and cmd != "load_commands"
        ] + ["config"]
        if module not in possible_modules:
            embed = get_enum_embed(
                possible_modules,
                title="List of reloadable modules"
            )
            await send_embed(message.channel, embed=embed)
        else:
            if module == "config":
                self.ctx.update_configs()
            elif module == "advanced":
                try:
                    self.ctx.load_commands(module, reload_module=True)
                except ImportError:
                    embed = get_embed(
                        "You need to purchase the Advanced Extension first.",
                        embed_type="error"
                    )
                    embed.set_footer(text="Please contact Hyper for details.")
                    await send_embed(message.channel, embed=embed)
            else:
                self.ctx.load_commands(module, reload_module=True)
            await send_embed(
                message.channel,
                embed=get_embed(
                    f"Successfully reloaded {module}."
                )
            )

    async def cmd_channel(
        self, message: Message,
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Set the active channel for the commands.
        $```scss
        {command_prefix}channel +/add/append channel_id
        {command_prefix}channel -/remove/del/delete channel_id
        {command_prefix}channel list
        {command_prefix}channel reset
        ```$

        @To prevent selfbot detection, we need to send commands in hidden channels
        and let the action take place in chosen channels.@

        ~To add channel with ID 1234 to selected channels list:
            ```
            {command_prefix}channel + 1234
            ```
        To remove channel with ID 1234 from selected channels list:
            ```
            {command_prefix}channel - 1234
            ```
        To display the selected channels list:
            ```
            {command_prefix}channel list
            ```
        To reset the selected channels list:
            ```
            {command_prefix}channel reset
            ```~
        """
        if len(args) >= 2:
            if args and all(dig.isdigit() for dig in args[1]):
                if args[0].lower() in ["+", "add", "append"]:
                    curr_chan = self.ctx.get_channel(int(args[1]))
                    self.ctx.active_channels.append(curr_chan)
                    self.logger.pprint(
                        f"Added {curr_chan}({curr_chan.id}) "
                        "to the list of selected channels.",
                        timestamp=True,
                        color="blue"
                    )
                elif args[0].lower() in ["-", "remove", "del", "delete"]:
                    curr_chan = self.ctx.get_channel(int(args[1]))
                    self.ctx.active_channels = [
                        chan
                        for chan in self.ctx.active_channels
                        if chan.id != curr_chan.id
                    ]
                    self.logger.pprint(
                        f"Removed {curr_chan}({curr_chan.id}) "
                        "from the list of selected channels.",
                        timestamp=True,
                        color="blue"
                    )
        elif args:
            if args[0].lower() == "list":
                await message.channel.send(
                    "\n".join(
                        f"{chan}({chan.id})" for chan in self.ctx.active_channels
                    )
                    or "None."
                )

            elif args[0].lower() == "reset":
                self.ctx.active_channels = []
                self.logger.pprint(
                    "All channels have been succesfully reset.",
                    timestamp=True,
                    color="green"
                )
