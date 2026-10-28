"""UtsClock: an estimate of the current UTS time.

RX timeouts are measured on the UTS clock, but UTS only reports time with received packets.
The estimate is: the last UTS timestamp seen + the host time elapsed since it was seen.
"""
import time
from typing import Optional


class UtsClock:
    def __init__(self):
        self._uts: Optional[float] = None
        self._host: Optional[float] = None

    def update(self, timestamp: Optional[float]) -> None:
        if timestamp is None:
            return
        if self._uts is None or timestamp >= self._uts:
            self._uts = timestamp
            self._host = time.monotonic()

    def now(self) -> Optional[float]:
        """Estimated UTS time; None until the first timestamp is seen."""
        if self._uts is None:
            return None
        return self._uts + (time.monotonic() - self._host)
