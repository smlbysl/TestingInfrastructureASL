"""Direction-specific state attached to a message object.

A message with RX has rx_state, a message with TX has tx_state; a bidirectional message has both.
The setting (Timing) is fixed; only changing values are kept here.
"""
import time
from dataclasses import dataclass, field
from typing import Optional

from asl_testing.message.timing import Timing


@dataclass
class RxState:
    timing: Timing
    timestamp: Optional[float] = None    # arrival time of the last valid packet, from UTS (seconds)
    last_time: Optional[float] = None    # host time of the last valid packet (time.monotonic)
    host_time: Optional[float] = None    # wall clock of this host at the last valid packet (time.time)
    count: int = 0                       # number of valid packets
    errors: int = 0                      # number of packets that failed validation
    created: float = field(default_factory=time.monotonic)   # host time the object was created
    _seen: int = 0                       # count at the last check_new() call

    def on_receive(self, timestamp: Optional[float] = None) -> None:
        self.timestamp = timestamp
        self.last_time = time.monotonic()
        self.host_time = time.time()
        self.count += 1

    def check_new(self) -> int:
        """Number of valid packets since the last call (0: none); the call clears it.

        count only grows (RX thread) and is read once here, so no packet is missed and no lock is needed.
        """
        count = self.count
        new = count - self._seen
        self._seen = count
        return new

    def on_error(self) -> None:
        self.errors += 1

    def age(self) -> Optional[float]:
        """Host time since the last packet; None if nothing has arrived yet."""
        if self.last_time is None:
            return None
        return time.monotonic() - self.last_time

    def is_fresh(self) -> bool:
        if self.last_time is None:
            return False                 # never arrived
        if not self.timing.is_periodic:
            return True                  # event message
        return self.age() <= self.timing.period * self.timing.tolerance


@dataclass
class TxState:
    timing: Timing
    last_time: Optional[float] = None    # host time of the last send (time.monotonic)
    count: int = 0

    def on_send(self) -> None:
        self.last_time = time.monotonic()
        self.count += 1
