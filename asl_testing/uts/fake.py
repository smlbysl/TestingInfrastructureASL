"""FakeUtsClient: stands in for UTS during development and tests."""
import threading
import time
from collections import defaultdict
from typing import Optional

from asl_testing.channel.channel import ProtocolType
from asl_testing.uts.client import FilterGroups, UtsClient, UtsFrame


class FakeUtsClient(UtsClient):
    """Stand-in for UTS during development and tests.

    transfer() records what is sent; inject() plays the device side and puts a packet
    into the receive buffer of a protocol + interface; fetch() drains that buffer, like UTS.
    Configs and filters are only stored (the filter is not applied to injected packets).
    """

    def __init__(self):
        self.sent: list[tuple[ProtocolType, int, bytes]] = []
        self._buffers: dict[tuple[ProtocolType, int], list[UtsFrame]] = defaultdict(list)
        self._lock = threading.Lock()         # inject (test thread) and fetch (RX poller) share the buffers
        self.configs: dict[tuple[ProtocolType, int], dict] = defaultdict(dict)
        self.filters: dict[tuple[ProtocolType, int], tuple[str, FilterGroups]] = {}

    def transfer(self, protocol: ProtocolType, interface: int, data: bytes) -> None:
        self.sent.append((protocol, interface, bytes(data)))

    def fetch(self, protocol: ProtocolType, interface: int) -> list[UtsFrame]:
        with self._lock:
            return self._buffers.pop((protocol, interface), [])

    def inject(self, protocol: ProtocolType, interface: int, data: bytes,
               timestamp: Optional[float] = None) -> None:
        stamp = time.time() if timestamp is None else timestamp
        with self._lock:
            self._buffers[(protocol, interface)].append(UtsFrame(bytes(data), stamp))

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
