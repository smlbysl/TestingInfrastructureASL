"""FakeUtsClient: stands in for UTS during development and tests."""
import threading
import time
from collections import defaultdict
from typing import Optional

from asl_testing.channel.channel import ProtocolType
from asl_testing.uts.client import UtsClient, UtsFrame


class FakeUtsClient(UtsClient):
    """Stand-in for UTS during development and tests.

    transfer() records what is sent; inject() plays the device side and puts a packet
    into the receive buffer of a protocol + interface; fetch() drains that buffer, like UTS.
    """

    def __init__(self):
        self.sent: list[tuple[ProtocolType, int, bytes]] = []
        self._buffers: dict[tuple[ProtocolType, int], list[UtsFrame]] = defaultdict(list)
        self._lock = threading.Lock()         # inject (test thread) and fetch (RX poller) share the buffers

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
