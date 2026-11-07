"""UTS client: the only place that knows how UTS is reached.

UTS is an HTTP service:
- POST transfers data on a protocol + interface.
- GET returns the messages buffered on a protocol + interface and empties that buffer.

The real HTTP client will be written when the UTS API is available. Open points (kept here only):
- JSON layout of the GET answer (a "messages" field with timestamp and data, plus some header info)
- data encoding (hex, base64, list of bytes)
- timestamp unit / resolution; this layer must return seconds as float
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from asl_testing.channel.channel import ProtocolType


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
