"""
Commands based on Statistics Module for Autocatcher.
"""

# pylint: disable=too-many-locals, unused-argument

from io import BytesIO
from typing import List, Optional

import discord
from discord import Message
from matplotlib import pyplot as plt

from ..helpers.stats_monitor import StatsMonitor
from ..helpers.utils import get_embed, send_embed
from .basecommand import Commands


class StatsCommands(Commands):
    '''
    Commands which use the StatsMonitor.
    Examples: Stats, Misses, Confidence
    '''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats = self.ctx.stats

    async def cmd_stats(self, message: Message, **kwargs):
        """Get the autocatcher statistics.
        $```scss
        {command_prefix}stats
        ```$

        @Display the statistics of the autocatcher like Catches/min, Accuracy.@

        ~To get the current stats:
            ```
            {command_prefix}stats
            ```~
        """
        elapsed = self.stats.elapsed()
        acc = self.stats.accuracy()
        total_spawned = self.stats.total_spawns()
        total_caught = self.stats.total_catches()
        spawn_rate = self.stats.spawns_rate(unit="min")
        catch_rate = self.stats.catches_rate(unit="min")
        most_spawned = self.stats.most_spawns()
        most_caught = self.stats.most_catches()
        stats_dict = {
            "Total spawned pokemons": total_spawned,
            "Spawn Rate": spawn_rate,
            "Most Spawned": most_spawned,
            "Total caught pokemons": total_caught,
            "Catch Rate": catch_rate,
            "Most Caught": most_caught,
            "Current Accuracy": acc
        }
        embed = get_embed(
            "\u200B",
            title="Realtime Autocatcher Stats"
        )
        for key, val in stats_dict.items():
            embed.add_field(name=key, value=val)
        embed.set_footer(text=elapsed)
        if len(set(self.stats.checkpoints["spawns"])) > 1:
            plt.clf()
            plt.figure(figsize=(10, 5))
            checkpoints = {**self.stats.checkpoints}
            duration = checkpoints.pop("duration")
            colors = ["tab:blue", "tab:green", "tab:red"]
            for metric, color in zip(checkpoints.values(), colors):
                plt.plot(duration, metric, color=color)
                plt.fill_between(duration, metric, color=color, alpha=0.8)
            plt.legend(list(checkpoints.keys()))
            plt.xlabel("Time(secs)->", fontsize=16)
            plt.ylabel("Count->", fontsize=16)
            plt.title("Stat Trends", fontsize=18)
            byio = BytesIO()
            plt.savefig(byio)
            byio.seek(0)
            stats_fl = discord.File(byio, "stats.jpg")
            embed.set_image(url="attachment://stats.jpg")
            await send_embed(message.channel, embed=embed, file=stats_fl)
        else:
            await send_embed(message.channel, embed=embed)

    async def cmd_misses(
        self, message: Message,
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Get the top 25 mispredicted pokemons.
        $```scss
        {command_prefix}misses [name]
        ```$

        @Display the image urls which were mispredicted.
        Results are sorted in descending order of number of links.
        You can get the links of a specific pokemon as well.@

        ~To get the top 25 misses:
            ```
            {command_prefix}misses
            ```
        To get the urls for a mispredicted Mewtwo:
            ```
            {command_prefix}misses Mewtwo
            ```~
        """
        names = []
        if args:
            name = args[0]
            names.append(name)
        else:
            names = sorted(
                list(self.stats.misses_map.keys()),
                key=lambda x: len(self.stats.misses_map[x]),
                reverse=True
            )[:25]
        embed = get_embed(
            "\u200B",
            embed_type="warning",
            title="Mispredicts"
        )
        misses = 0
        for name in names:
            urls = self.stats.get_misses_urls(name)
            if urls:
                misses += 1
                embed.add_field(
                    name=name,
                    value="\n".join(urls),
                    inline=False
                )
        if not misses:
            embed.description = "Woah, not a single miss till now!"
        await send_embed(message.channel, embed=embed)

    async def cmd_confidence(
        self, message: Message,
        args: Optional[List[str]] = None,
        **kwargs
    ):
        """Get the confidence levels of the correctly predicted pokemons.
        $```scss
        {command_prefix}confidence [name]
        ```$

        @Display the confidence levels of the bottom 25 caught pokemons.
        Results are sorted in ascending order of confidence.
        You can get the confidence of a specific pokemon as well.@

        ~To get the bottom 25 confidence levels:
            ```
            {command_prefix}confidence
            ```
        To get the confidence of correctly caught Arceus:
            ```
            {command_prefix}confidence Arceus
            ```~
        """
        names = []
        if args:
            name = args[0]
            names.append(name)
        else:
            names = sorted(
                list(self.stats.confidence_map.keys()),
                key=lambda x: float(self.stats.confidence_map[x])
            )[:25]
        embed = get_embed(
            "\u200B",
            title="Confidence Levels"
        )
        confs = 0
        for name in names:
            conf = self.stats.get_confidence(name)
            conf = conf * 100
            if conf:
                confs += 1
                embed.add_field(
                    name=name,
                    value=f"{conf:2.2f}%"
                )
        if not confs:
            embed.description = "Yet to catch some pokemons."
        await send_embed(message.channel, embed=embed)

    async def cmd_reset_stats(
        self, message: Message,
        **kwargs
    ):
        """Reset the autocatcher statistics.
        $```scss
        {command_prefix}reset_stats
        ```$

        @Resets the statistics of the autocatcher like Catches/min, Accuracy.@

        ~To reset the current stats:
            ```
            {command_prefix}reset_stats
            ```~
        """
        self.stats = self.ctx.stats = StatsMonitor(self.ctx)
        self.ctx.loop.create_task(self.stats.checkpointer())
        self.logger.pprint(
            "Succesfully reset the stats to a fresh start.",
            color="green",
            timestamp=True
        )
