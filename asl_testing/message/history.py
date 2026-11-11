"""Received packets of a message, kept in order (the last N).

The live object shows only the last packet. When several packets of a message arrive in one UTS poll,
the values in between are visible only here.

    mark = status.rx_history.mark()                    # only packets after this point count
    ...
    for rec in status.rx_history.since(mark):          # every packet since mark, oldest first
        print(rec.seq, rec.timestamp, rec.snapshot().speed)

Reading never removes records: each reader keeps its own mark, so two readers do not affect each other.
A record holds the packet as the ctypes layout of the message; snapshot() turns it into a separate object.
"""
import itertools
import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

_log = logging.getLogger(__name__)
_seq = itertools.count(1)               # one order for all messages; next() is atomic under the GIL


def next_seq() -> int:
    return next(_seq)


@dataclass(frozen=True)
class Record:
    """One received packet. Never changes."""
    seq: int                            # global order: a larger seq arrived later (over all messages)
    timestamp: Optional[float]          # arrival time reported by UTS (seconds)
    host_time: float                    # wall clock of this host when it was decoded (time.time)
    image: bytes                        # the packet in the message's ctypes layout
    cls: type                           # message class, to read the image

    def snapshot(self):
        """A separate object with the values of this packet (not registered, no channel / state)."""
        return self.cls.from_buffer_copy(self.image)


class MessageHistory:
    """The last `capacity` records of one message; the oldest is dropped when it is full."""

    def __init__(self, capacity: int, name: str = ""):
        if capacity < 1:
            raise ValueError("history capacity must be at least 1")
        self.capacity = capacity
        self.name = name                # for the overflow warning
        self.dropped = 0                # records pushed out by newer ones
        self._records: deque[Record] = deque(maxlen=capacity)
        self._cond = threading.Condition()

    def push(self, record: Record) -> None:
        """Called by the RX thread for every valid packet."""
        with self._cond:
            if len(self._records) == self.capacity:
                self.dropped += 1
                if self.dropped == 1:               # once per history, not for every packet
                    _log.warning("history of %s is full (%d records): older packets are dropped",
                                 self.name or "message", self.capacity)
            self._records.append(record)
            self._cond.notify_all()

    def mark(self) -> int:
        """The current position: since(mark) / wait_for(after=mark) see only packets after it."""
        with self._cond:
            return self._records[-1].seq if self._records else 0

    def since(self, mark: int) -> list[Record]:
        """Records after mark, oldest first."""
        with self._cond:
            return [r for r in self._records if r.seq > mark]

    def last(self) -> Optional[Record]:
        with self._cond:
            return self._records[-1] if self._records else None

    def wait_for(self, predicate: Callable[[object], bool], after: int, timeout: float) -> Optional[Record]:
        """The first record after `after` whose snapshot satisfies predicate; None on timeout.

        Wakes up when a record arrives (no polling). predicate gets the snapshot: lambda s: s.speed == 10.
        """
        found: list[Record] = []
        checked = after                                 # records up to here were already tested

        def check() -> bool:
            nonlocal checked
            for record in self._records:
                if record.seq > checked:
                    checked = record.seq
                    if predicate(record.snapshot()):
                        found.append(record)
                        return True
            return False

        with self._cond:
            self._cond.wait_for(check, timeout)
        return found[0] if found else None

    def clear(self) -> None:
        with self._cond:
            self._records.clear()
            self.dropped = 0

    def __len__(self) -> int:
        with self._cond:
            return len(self._records)
