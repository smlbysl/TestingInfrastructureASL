"""FakeUtsClient: UTS stand-in for development and tests."""

__author__ = "İsmail Baysal"
import threading
import time
from collections import defaultdict
from typing import Optional

from asl_testing.channel.channel import ProtocolType
from asl_testing.protocol.defaults import default_protocols
from asl_testing.uts.client import FilterGroups, UtsClient, UtsFrame


class FakeUtsClient(UtsClient):
    """post() / transfer() record what is sent; inject() plays the device; get() / fetch() drain the buffer.

    inject() stores the item UTS would return (protocol.simulate). Configs and filters are only
    stored; the filter is not applied.
    """

    def __init__(self):
        self.sent: list[tuple[ProtocolType, int, bytes]] = []          # transfer()
        self.posted: list[tuple[str, int, dict]] = []                  # post()
        self.protocols = default_protocols()
        self._buffers: dict[tuple[ProtocolType, int], list[UtsFrame]] = defaultdict(list)
        self._items: dict[tuple[str, int], list[dict]] = defaultdict(list)
        self._lock = threading.Lock()         # inject (test thread) vs get (RX thread)
        self.configs: dict[tuple[ProtocolType, int], dict] = defaultdict(dict)
        self.filters: dict[tuple[ProtocolType, int], tuple[str, FilterGroups]] = {}

    def transfer(self, protocol: ProtocolType, interface: int, data: bytes) -> None:
        self.sent.append((protocol, interface, bytes(data)))

    def fetch(self, protocol: ProtocolType, interface: int) -> list[UtsFrame]:
        with self._lock:
            return self._buffers.pop((protocol, interface), [])

    def post(self, path: str, interface: int, body: dict) -> None:
        self.posted.append((path, interface, dict(body)))

    def get(self, path: str, interface: int) -> list[dict]:
        with self._lock:
            return self._items.pop((path, interface), [])

    def inject(self, protocol: ProtocolType, interface: int, data: bytes,
               timestamp: Optional[float] = None) -> None:
        """The device sent data (bytes on the line)."""
        stamp = time.time() if timestamp is None else timestamp
        handler = self.protocols.get(protocol)
        with self._lock:
            if handler is None:
                self._buffers[(protocol, interface)].append(UtsFrame(bytes(data), stamp))
            else:
                self._items[(handler.path, interface)].append(handler.simulate(bytes(data), stamp))

    # ---------------------------------------------------------------- management

    def get_config(self, protocol: ProtocolType, interface: int) -> dict:
        return dict(self.configs[(protocol, interface)])

    def set_config(self, protocol: ProtocolType, interface: int, settings: dict) -> None:
        self.configs[(protocol, interface)].update(settings)

    def get_filter(self, protocol: ProtocolType, interface: int) -> tuple[str, FilterGroups]:
        kind, groups = self.filters.get((protocol, interface), ("NONE", []))
        return kind, [list(g) for g in groups]

    def set_filter(self, protocol: ProtocolType, interface: int, kind: str, groups: FilterGroups) -> None:
        self.filters[(protocol, interface)] = (kind, [list(g) for g in groups])
