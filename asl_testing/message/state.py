"""RX / TX state of a message object: the values that change while it is used.

count is written only by the RX (or TX) thread and read once by check_new / check_sent,
so no packet is lost between two checks and no lock is needed.
"""

__author__ = "İsmail Baysal"

import time
from dataclasses import dataclass, field
from typing import Optional

from asl_testing.message.history import MessageHistory
from asl_testing.message.timing import Timing


@dataclass
class RxState:
    timing: Timing
    timestamp: Optional[float] = None    # UTS time of the last valid packet (seconds)
    last_time: Optional[float] = None    # host time of the last valid packet (time.monotonic)
    host_time: Optional[float] = None    # host time of the last valid packet (time.time)
    count: int = 0                       # valid packets
    errors: int = 0                      # packets that failed validation
    created: float = field(default_factory=time.monotonic)
    history: Optional[MessageHistory] = None
    _seen: int = 0                       # count at the last check_new()

    def on_receive(self, timestamp: Optional[float] = None) -> None:
        self.timestamp = timestamp
        self.last_time = time.monotonic()
        self.host_time = time.time()
        self.count += 1

    def check_new(self) -> int:
        """Valid packets since the last call; clears the count."""
        count = self.count
        new = count - self._seen
        self._seen = count
        return new

    def peek_new(self) -> int:
        """Like check_new() without clearing."""
        return self.count - self._seen

    def on_error(self) -> None:
        self.errors += 1

    def age(self) -> Optional[float]:
        """Seconds since the last packet, or None."""
        if self.last_time is None:
            return None
        return time.monotonic() - self.last_time

    def is_fresh(self) -> bool:
        if self.last_time is None:
            return False
        if not self.timing.is_periodic:
            return True
        return self.age() <= self.timing.period * self.timing.tolerance


@dataclass
class TxState:
    timing: Timing
    last_time: Optional[float] = None    # host time of the last successful send (time.monotonic)
    count: int = 0                       # successful sends
    _seen: int = 0                       # count at the last check_sent()

    def on_send(self) -> None:
        self.last_time = time.monotonic()
        self.count += 1

    def check_sent(self) -> int:
        """Successful sends since the last call; clears the count."""
        count = self.count
        new = count - self._seen
        self._seen = count
        return new

    def peek_sent(self) -> int:
        """Like check_sent() without clearing."""
        return self.count - self._seen
