"""UTS client: the only place that knows how UTS is reached.

UTS is an HTTP service:
- POST transfers data on a protocol + interface.
- GET returns the messages buffered on a protocol + interface and empties that buffer.

The real HTTP client will be written when the UTS API is available. Open points (kept here only):
- JSON layout of the GET answer (a "messages" field with timestamp and data, plus some header info)
- data encoding (hex, base64, list of bytes)
- timestamp unit / resolution; this layer must return seconds as float
"""
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from generic.enumerations import ProtocolType


@dataclass(frozen=True)
class UtsFrame:
    data: bytes
    timestamp: Optional[float]          # UTS arrival time in seconds


class UtsClient(ABC):
    @abstractmethod
    def transfer(self, protocol: ProtocolType, interface: int, data: bytes) -> None:
        """Sends data on the given protocol + interface (HTTP POST)."""

    @abstractmethod
    def fetch(self, protocol: ProtocolType, interface: int) -> list[UtsFrame]:
        """Returns the messages received since the last call (HTTP GET)."""


class HttpUtsClient(UtsClient):
    """Placeholder for the real UTS client."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    def transfer(self, protocol: ProtocolType, interface: int, data: bytes) -> None:
        raise NotImplementedError("UTS API not integrated yet")

    def fetch(self, protocol: ProtocolType, interface: int) -> list[UtsFrame]:
        raise NotImplementedError("UTS API not integrated yet")


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
