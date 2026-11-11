"""UtsClock: estimate of the current UTS time for RX timeouts.

UTS reports time only with packets, so: last UTS timestamp + host time passed since then.
"""

__author__ = "İsmail Baysal"
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
        """Estimated UTS time, or None before the first timestamp."""
        if self._uts is None:
            return None
        return self._uts + (time.monotonic() - self._host)
