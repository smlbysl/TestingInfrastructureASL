"""FakeUtsAdapter: UTS stand-in for development and tests (keeps the UTS JSON)."""

__author__ = "İsmail Baysal"

import threading
import time
from collections import defaultdict
from typing import Optional

from asl_testing.channel.channel import Channel
from asl_testing.adapter.base import FilterGroups
from asl_testing.adapter.uts.adapter import UtsAdapter


class FakeUtsAdapter(UtsAdapter):
    """post() records what is sent; inject() plays the device; get() drains the receive buffer.

    inject() stores the item UTS would return, built by the protocol definition (protocol.simulate).
    Configs and filters are only stored; the filter is not applied.
    """

    def __init__(self, time_unit: float = 1.0, timeout: Optional[float] = None, log=None):
        super().__init__(time_unit, timeout, log)
        self.posted: list[tuple[str, int, dict]] = []                  # (path, interface, body)
        self._items: dict[tuple[str, int], list[dict]] = defaultdict(list)
        self._items_lock = threading.Lock()   # inject (test thread) vs get (RX thread)
        self.configs: dict[tuple[str, int], dict] = defaultdict(dict)
        self.filters: dict[tuple[str, int], tuple[str, FilterGroups]] = {}

    def post(self, path: str, interface: int, body: dict, timeout: float = 0.0) -> None:
        self.posted.append((path, interface, dict(body)))

    def get(self, path: str, interface: int, timeout: float = 0.0) -> list[dict]:
        with self._items_lock:
            return self._items.pop((path, interface), [])

    def inject(self, channel: Channel, data: bytes, timestamp: Optional[float] = None) -> None:
        """The device sent data (bytes on the line) on the channel's interface."""
        stamp = time.time() if timestamp is None else timestamp
        protocol = self.protocol(channel)
        item = protocol.simulate(channel, bytes(data), stamp)
        with self._items_lock:
            self._items[(protocol.path, channel.interface)].append(item)     # where get() looks

    # ---------------------------------------------------------------- config and filter requests

    def read_config(self, path: str, interface: int) -> dict:
        return dict(self.configs[(path, interface)])

    def write_config(self, path: str, interface: int, settings: dict) -> None:
        self.configs[(path, interface)].update(settings)

    def read_filter(self, path: str, interface: int) -> tuple[str, FilterGroups]:
        kind, groups = self.filters.get((path, interface), ("NONE", []))
        return kind, [list(g) for g in groups]

    def write_filter(self, path: str, interface: int, kind: str, groups: FilterGroups) -> None:
        self.filters[(path, interface)] = (kind, [list(g) for g in groups])
