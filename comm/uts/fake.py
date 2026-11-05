"""FakeUtsClient: stands in for UTS during development and tests.

- transfer() records what is sent (sent)
- inject() plays the device side: puts a packet into the receive buffer of a link
- fetch() drains that buffer, like UTS
- preset() sets the settings UTS "already has" (for config_mode = "manual")
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any, Optional

from comm.link import Link
from comm.uts.base import FilterGroups, UtsClient, UtsFetch, UtsFrame


class FakeUtsClient(UtsClient):
    def __init__(self):
        self.sent: list[tuple[Link, bytes]] = []
        self.configs: dict[tuple[str, int], dict[str, Any]] = {}
        self.filters: dict[tuple[str, int], tuple[str, FilterGroups]] = {}
        self.overflow: set[tuple[str, int]] = set()     # links whose next fetch reports an overflow
        self._buffers: dict[tuple[str, int], list[UtsFrame]] = defaultdict(list)
        self._lock = threading.Lock()                   # inject (test thread) and fetch (RX thread)

    def read_config(self, link: Link) -> tuple[dict[str, Any], dict[str, Any]]:
        key = (link.bus, link.interface)
        config = self.configs.get(key) or type(link)(name=link.name, interface=link.interface).to_uts()
        return dict(config), {"isOpen": True, "deviceName": f"FAKE-{link.bus}-{link.interface}"}

    def write_config(self, link: Link) -> None:
        self.configs[(link.bus, link.interface)] = link.to_uts()

    def transfer(self, link: Link, data: bytes) -> None:
        self.sent.append((link, bytes(data)))

    def fetch(self, link: Link) -> UtsFetch:
        key = (link.bus, link.interface)
        with self._lock:
            frames = self._buffers.pop(key, [])
            overflow = key in self.overflow
            self.overflow.discard(key)
        return UtsFetch(frames, overflow)

    def write_filter(self, link: Link, kind: str, groups: FilterGroups) -> None:
        self.filters[(link.bus, link.interface)] = (kind, groups)

    # ---------------------------------------------------------------- device side

    def inject(self, link: Link, data: bytes, timestamp: Optional[float] = None) -> None:
        stamp = time.time() if timestamp is None else timestamp
        with self._lock:
            self._buffers[(link.bus, link.interface)].append(UtsFrame(bytes(data), stamp))

    def preset(self, bus: str, interface: int, config: dict[str, Any]) -> None:
        self.configs[(bus, interface)] = dict(config)
