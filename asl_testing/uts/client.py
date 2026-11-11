"""UtsClient: how UTS is reached (UTS is an HTTP service).

POST sends on a protocol + interface; GET returns what was received there and empties the buffer.

    post / get          JSON; the body and the items are built and read by the protocol object
    transfer / fetch    raw bytes, for a channel type without a protocol object

Open until the UTS API is available: JSON layout of GET, timestamp unit, body of config and filter
calls (master: {"type": kind, "filter": [[{"filterBytePos", "filterValue"}]]}).
"""

__author__ = "İsmail Baysal"
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from asl_testing.channel.channel import ProtocolType


class UtsError(Exception):
    """A UTS request failed (HTTP error, status not OK, UTS unreachable)."""


FilterGroups = list[list[tuple[int, int]]]   # OR of groups; a group is an AND of (byte position, value)


@dataclass(frozen=True)
class UtsFrame:
    data: bytes
    timestamp: Optional[float]          # UTS time in seconds


class UtsClient(ABC):
    @abstractmethod
    def transfer(self, protocol: ProtocolType, interface: int, data: bytes) -> None:
        """Sends raw bytes (HTTP POST)."""

    @abstractmethod
    def fetch(self, protocol: ProtocolType, interface: int) -> list[UtsFrame]:
        """Raw packets received since the last call (HTTP GET)."""

    # ---------------------------------------------------------------- JSON level

    def post(self, path: str, interface: int, body: dict) -> None:
        """POST /{path}/{interface}/messages with the body from the protocol."""
        raise NotImplementedError

    def get(self, path: str, interface: int) -> list[dict]:
        """GET /{path}/{interface}/messages: items received since the last call."""
        raise NotImplementedError

    # ---------------------------------------------------------------- management (optional)

    def get_config(self, protocol: ProtocolType, interface: int) -> dict:
        """Settings of an interface."""
        raise NotImplementedError

    def set_config(self, protocol: ProtocolType, interface: int, settings: dict) -> None:
        """Writes settings of an interface."""
        raise NotImplementedError

    def get_filter(self, protocol: ProtocolType, interface: int) -> tuple[str, FilterGroups]:
        """Receive filter as (kind, groups); kind "NONE" means no filter."""
        raise NotImplementedError

    def set_filter(self, protocol: ProtocolType, interface: int, kind: str, groups: FilterGroups) -> None:
        """kind "INCLUSIVE": only the groups pass; "NONE": no filter."""
        raise NotImplementedError
