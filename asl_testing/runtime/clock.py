"""UtsClock: estimate of the current UTS time for RX timeouts.

UTS reports time only with packets, so: last UTS timestamp + host time passed since then.
Updated by the RX thread of every channel, read by the watchdog.
"""

__author__ = "İsmail Baysal"
import threading
import time
from typing import Optional


class UtsClock:
    def __init__(self):
        self._lock = threading.Lock()
        self._uts: Optional[float] = None
        self._host: Optional[float] = None

    def update(self, timestamp: Optional[float]) -> None:
        if timestamp is None:
            return
        with self._lock:
            if self._uts is None or timestamp >= self._uts:
                self._uts = timestamp
                self._host = time.monotonic()

    def now(self) -> Optional[float]:
        """Estimated UTS time, or None before the first timestamp."""
        with self._lock:
            if self._uts is None:
                return None
            return self._uts + (time.monotonic() - self._host)
