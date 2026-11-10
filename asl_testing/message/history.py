"""Bounded history of message images (ring buffer), one per direction of a message object.

A record holds one packet as the ctypes layout of the message (image), so any field can be read later
with record.snapshot(). Records never change. Readers keep their own position (seq) with mark(), so
nobody consumes anybody's data (unlike has_new()).

    mark = status.rx_history.mark()                  # only packets after this point count
    comm.send(request)
    rec = comm.wait_for(status, lambda s: s.speed == 10, after=mark)
    for r in status.rx_history.since(mark):          # every packet since mark, in order
        print(r.seq, r.timestamp, r.snapshot().speed)

The oldest records are dropped when the history is full; `dropped` counts them.
"""
from __future__ import annotations

import itertools
import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

_seq = itertools.count(1)               # global and monotonic; next() is atomic under the GIL


def next_seq() -> int:
    return next(_seq)


@dataclass(frozen=True)
class Record:
    seq: int                            # global order of records (packets of one poll share a timestamp)
    timestamp: Optional[float]          # UTS time in seconds (RX); None for TX
    host_time: float                    # wall clock of this host (time.time)
    image: bytes                        # ctypes layout of the message
    cls: type                           # message class, to read the image

    def snapshot(self):
        """A separate object of the message class holding the values of this packet.

        It is not registered and has no object information (channel, PCI, states): read field values only.
        """
        return self.cls.from_buffer_copy(self.image)


class MessageHistory:
    def __init__(self, capacity: int = 64):
        if capacity < 1:
            raise ValueError("history capacity must be at least 1")
        self._buf: deque[Record] = deque(maxlen=capacity)
        self._cond = threading.Condition()
        self.dropped = 0                # records pushed out by newer ones

    @property
    def capacity(self) -> int:
        return self._buf.maxlen

    def __len__(self) -> int:
        with self._cond:
            return len(self._buf)

    def push(self, record: Record) -> None:
        with self._cond:
            if len(self._buf) == self._buf.maxlen:
                self.dropped += 1
            self._buf.append(record)
            self._cond.notify_all()

    def mark(self) -> int:
        """Position to read or wait from: only records after it count. Use it before a request."""
        with self._cond:
            return self._buf[-1].seq if self._buf else 0

    def since(self, seq: int = 0) -> list[Record]:
        """Records after position seq, oldest first."""
        with self._cond:
            return [r for r in self._buf if r.seq > seq]

    def last(self) -> Optional[Record]:
        with self._cond:
            return self._buf[-1] if self._buf else None

    def wait_for(self, predicate: Callable[[object], bool], after: int, timeout: float) -> Optional[Record]:
        """First record after `after` whose snapshot satisfies predicate; None on timeout.

        Wakes up when a record is pushed (no polling). The predicate gets a snapshot: lambda s: s.speed == 10.
        """
        found: list[Record] = []
        checked = after

        def check() -> bool:
            nonlocal checked
            for r in self._buf:
                if r.seq > checked:
                    checked = r.seq
                    if predicate(r.snapshot()):
                        found.append(r)
                        return True
            return False

        with self._cond:
            self._cond.wait_for(check, timeout)
        return found[0] if found else None

    def clear(self) -> None:
        with self._cond:
            self._buf.clear()
            self.dropped = 0
