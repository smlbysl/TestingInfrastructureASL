"""UTS client: the only place that knows how UTS is reached.

UTS is an HTTP service:
- POST transfers data on a protocol + interface.
- GET returns the messages buffered on a protocol + interface and empties that buffer.

The real HTTP client will be written when the UTS API is available. Open points (kept here only):
- JSON layout of the GET answer (a "messages" field with timestamp and data, plus some header info)
- data encoding (hex, base64, list of bytes)
- timestamp unit / resolution; this layer must return seconds as float
- body layout of configs and filters (master: {"type": kind, "filter": [[{"filterBytePos", "filterValue"}]]})
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from asl_testing.channel.channel import ProtocolType


class UtsError(Exception):
    """A UTS request failed (HTTP error, statusInfo not OK, UTS unreachable)."""


FilterGroups = list[list[tuple[int, int]]]   # OR of groups, each an AND of (byte position on the line, value)


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

    # ---------------------------------------------------------------- management (optional)
    # Not abstract: a client without them keeps working; only these calls raise NotImplementedError.

    def get_config(self, protocol: ProtocolType, interface: int) -> dict:
        """Settings of an interface (HTTP GET configs)."""
        raise NotImplementedError

    def set_config(self, protocol: ProtocolType, interface: int, settings: dict) -> None:
        """Writes settings of an interface (HTTP POST configs)."""
        raise NotImplementedError

    def get_filter(self, protocol: ProtocolType, interface: int) -> tuple[str, FilterGroups]:
        """Receive filter of an interface as (kind, groups); kind "NONE": no filter.
        The client converts the UTS answer into this form, so it can be changed and written back."""
        raise NotImplementedError

    def set_filter(self, protocol: ProtocolType, interface: int, kind: str, groups: FilterGroups) -> None:
        """kind: "INCLUSIVE" (only the groups pass) or "NONE" (no filter)."""
        raise NotImplementedError
