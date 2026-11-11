"""FakeUtsClient: UTS stand-in for development and tests."""

__author__ = "İsmail Baysal"

import threading
import time
from collections import defaultdict
from typing import Optional

from asl_testing.channel.channel import Channel
from asl_testing.uts.client import FilterGroups, UtsClient


class FakeUtsClient(UtsClient):
    """post() records what is sent; inject() plays the device; get() drains the receive buffer.

    inject() stores the item UTS would return, built by the channel's protocol (protocol.simulate).
    Configs and filters are only stored; the filter is not applied.
    """

    def __init__(self):
        self.posted: list[tuple[str, int, dict]] = []                  # (path, interface, body)
        self._items: dict[tuple[str, int], list[dict]] = defaultdict(list)
        self._lock = threading.Lock()         # inject (test thread) vs get (RX thread)
        self.configs: dict[tuple[str, int], dict] = defaultdict(dict)
        self.filters: dict[tuple[str, int], tuple[str, FilterGroups]] = {}

    def post(self, path: str, interface: int, body: dict) -> None:
        self.posted.append((path, interface, dict(body)))

    def get(self, path: str, interface: int) -> list[dict]:
        with self._lock:
            return self._items.pop((path, interface), [])

    def inject(self, channel: Channel, data: bytes, timestamp: Optional[float] = None) -> None:
        """The device sent data (bytes on the line) on the channel's interface."""
        stamp = time.time() if timestamp is None else timestamp
        item = channel.protocol.simulate(bytes(data), stamp)
        with self._lock:
            self._items[channel.key].append(item)

    # ---------------------------------------------------------------- management

    def get_config(self, path: str, interface: int) -> dict:
        return dict(self.configs[(path, interface)])

    def set_config(self, path: str, interface: int, settings: dict) -> None:
        self.configs[(path, interface)].update(settings)

    def get_filter(self, path: str, interface: int) -> tuple[str, FilterGroups]:
        kind, groups = self.filters.get((path, interface), ("NONE", []))
        return kind, [list(g) for g in groups]

    def set_filter(self, path: str, interface: int, kind: str, groups: FilterGroups) -> None:
        self.filters[(path, interface)] = (kind, [list(g) for g in groups])
