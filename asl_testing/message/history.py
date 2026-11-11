"""Message history: the last N received packets of a message, in order.

The object shows only the last packet; packets that arrive together in one UTS poll are all kept here.
Reading does not remove records, so every reader keeps its own mark.

    mark = status.rx_history.mark()
    ...
    for rec in status.rx_history.since(mark):
        print(rec.seq, rec.timestamp, rec.snapshot().speed)
"""

__author__ = "İsmail Baysal"

import itertools
import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

_log = logging.getLogger(__name__)
_seq = itertools.count(1)               # one order for all messages


def next_seq() -> int:
    return next(_seq)


@dataclass(frozen=True)
class Record:
    """One received packet."""
    seq: int                            # arrival order over all messages
    timestamp: Optional[float]          # UTS time in seconds
    host_time: float                    # host time (time.time)
    image: bytes                        # ctypes layout of the message
    cls: type                           # message class

    def snapshot(self):
        """Separate object with the values of this packet (not registered, no channel or state)."""
        return self.cls.from_buffer_copy(self.image)


class MessageHistory:
    """Last `capacity` records of one message; the oldest is dropped when full."""

    def __init__(self, capacity: int, name: str = ""):
        if capacity < 1:
            raise ValueError("history capacity must be at least 1")
        self.capacity = capacity
        self.name = name
        self.dropped = 0                # records pushed out by newer ones
        self._records: deque[Record] = deque(maxlen=capacity)
        self._cond = threading.Condition()

    def push(self, record: Record) -> None:
        """Adds a record (RX thread). Warns once when the first record is dropped."""
        with self._cond:
            if len(self._records) == self.capacity:
                self.dropped += 1
                if self.dropped == 1:
                    _log.warning("history of %s is full (%d records): older packets are dropped",
                                 self.name or "message", self.capacity)
            self._records.append(record)
            self._cond.notify_all()

    def mark(self) -> int:
        """Current position; since() and wait_for() look only after it."""
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
        """First record after `after` whose snapshot satisfies predicate, or None on timeout.

        Wakes up when a record arrives. Each record is tested once.
        """
        found: list[Record] = []
        checked = after

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
