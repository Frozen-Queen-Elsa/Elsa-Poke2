"""
Autocatcher Statistics Monitor Module
"""

# pylint: disable=too-many-instance-attributes

from __future__ import annotations
import asyncio
from datetime import datetime
from functools import partial
from typing import List, TYPE_CHECKING

from .utils import get_formatted_time

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from pokeball import PokeBall


class StatsMonitor:
    """
    The stats monitor class
    Metrics:
        Catches, Spawns, Misses
    """
    def __init__(
        self, ctx: PokeBall,
        *args, **kwargs
    ):
        self.ctx = ctx
        self.logger = self.ctx.logger
        self.start_time = datetime.now()
        self.spawns = []
        self.catches = []
        self.misses = []
        self.checkpoints = {}
        self.confidence_map = {}
        self.misses_map = {}
        for iterable in ["spawns", "catches", "misses"]:
            mapper = {
                f"{iterable}_rate": partial(self.get_rate, iterable, **kwargs),
                f"update_{iterable}": partial(self.update, iterable, *args),
                f"total_{iterable}": partial(self.total, iterable),
                f"most_{iterable}": partial(self.most, iterable)
            }
            for key, val in mapper.items():
                setattr(self, key, val)

    def calc_rate(self, metric: List[str], unit: str = "sec"):
        """
        Calculate metric per unit time.
        Time unit defaults to seconds.
        """
        curr_time = datetime.now()
        time_diff = (curr_time - self.start_time).total_seconds()
        rate = len(metric) / time_diff
        if unit.lower() in {"hr", "hour"}:
            rate = rate * 3600
        elif unit.lower() in {"min", "minute"}:
            rate = rate * 60
        return rate

    def get_rate(self, iterable: List, **kwargs):
        """
        Readable wrapper for calc_rate.
        """
        metric = getattr(self, iterable)
        unit = kwargs.get("unit", "sec")
        rate = self.calc_rate(metric, unit=unit)
        return f"{rate:2.2f} {iterable}/{unit}"

    def update(self, iterable: List[str], elem: str):
        """
        Adds the element to the given metric iterable.
        """
        getattr(self, iterable).append(elem)

    def total(self, iterable: List[str]):
        """
        Computes the total for a metric.
        """
        return len(getattr(self, iterable))

    def most(self, iterable: List):
        """
        Returns the most common element in the metric.
        """
        metric = getattr(self, iterable)
        try:
            most = sorted(
                metric,
                key=metric.count,
                reverse=True
            )[0]
            if metric.count(most) < 2:
                return "None"
            return f"{most}({metric.count(most)} times)"
        except IndexError:
            return "None"

    def elapsed(self):
        """
        Returns elapsed time since the init of stats monitor.
        """
        try:
            elapsed = self.checkpoints["duration"][-1]
        except IndexError:
            elapsed = 0
        return f"Time Elapsed: {get_formatted_time(elapsed)}"

    def accuracy(self):
        """
        Returns the Catches vs Spawns Ratio
        """
        if len(self.spawns) <= 0:
            return "No spawns yet"

        acc = (len(self.catches) / len(self.spawns)) * 100
        return f"{acc:.2f}%"

    def get_confidence(self, name: str):
        """
        Get the average confidence for a particular pokemon.
        """
        return self.confidence_map.get(name.title(), 0.0)

    def update_confidence(self, name: str, conf: float):
        """
        Update the confidence for a particular pokemon.
        """
        if not self.confidence_map.get(name.title(), False):
            self.confidence_map[name.title()] = conf
        else:
            avg = (self.confidence_map[name.title()] + conf) / 2
            self.confidence_map.update({name.title(): avg})

    def get_misses_urls(self, name: str):
        """
        Returns a list of image urls per mis-predicted pokemon.
        """
        return self.misses_map.get(name.title(), [])

    def update_misses_urls(self, name: str, url: str):
        """
        Updates the list of image urls for a mis-predicted pokemon.
        """
        if not self.get_misses_urls(name):
            self.misses_map[name.title()] = [url]
        else:
            self.misses_map[name.title()].append(url)

    def checkpoint(self):
        """
        Create a metrics checkpoint along with time elapsed.
        """
        elapsed = (datetime.now() - self.start_time).total_seconds()
        self.logger.pprint(
            f"{get_formatted_time(elapsed)} have passed.\n"
            "Creating a statistical checkpoint.",
            color="blue",
            timestamp=True
        )
        if not self.checkpoints:
            self.checkpoints = {"duration": [elapsed]}
            self.checkpoints.update({
                iterable: [self.total(iterable)]
                for iterable in ["spawns", "catches", "misses"]
            })
        else:
            self.checkpoints["duration"].append(elapsed)
            for iterable in ["spawns", "catches", "misses"]:
                self.checkpoints[iterable].append(self.total(iterable))

    async def checkpointer(self, duration: int = 300):
        """
        Asynchronous handler for stats monitor checkpointing.
        """
        while self.ctx.autocatcher_enabled:
            self.checkpoint()
            await asyncio.sleep(duration)
