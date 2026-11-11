"""Timing and direction settings of a message."""

__author__ = "İsmail Baysal"

from dataclasses import dataclass
from enum import Flag, auto
from typing import Optional


@dataclass(frozen=True)
class Timing:
    """period None: event message; otherwise periodic. Frozen, so one default can be shared."""
    period: Optional[float] = None       # seconds
    tolerance: float = 2.0               # RX is late after period * tolerance

    @property
    def is_periodic(self) -> bool:
        return self.period is not None


class Direction(Flag):
    RX = auto()
    TX = auto()
    BOTH = RX | TX
