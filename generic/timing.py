"""Timing: the timing setting of a message (immutable).

- period None means the message is event based, otherwise it is periodic.
- Frozen, so a project default can be shared between all objects.
- Changing values (last arrival/send time, counters) live in RxState / TxState.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Timing:
    period: Optional[float] = None       # seconds; None -> event
    tolerance: float = 2.0               # RX: late when period * tolerance is exceeded

    @property
    def is_periodic(self) -> bool:
        return self.period is not None
