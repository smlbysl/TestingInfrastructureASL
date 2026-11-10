"""UTS client: the only place that knows how UTS is reached. JSON in and out, nothing about protocols.

UTS is an HTTP service (Windows) that talks to the hardware over serial lines or Ethernet:
- POST /{path}/{interface}/messages sends one item (body: JSON)
- GET  /{path}/{interface}/messages returns the items buffered since the last call and empties the buffer
How a protocol's PDU is written in that JSON is the job of the gateway adapters (uts/adapters.py).
The path is the protocol's bus name ("ethernet", "serials", "1553", "can").

Open points (kept here only): the real answer layout of GET, the timestamp unit, the body layout of
configs and filters (master: {"type": kind, "filter": [[{"filterBytePos", "filterValue"}]]}).
"""
from abc import ABC, abstractmethod


class UtsError(Exception):
    """A UTS request failed (HTTP error, statusInfo not OK, UTS unreachable, unexpected answer)."""


FilterGroups = list[list[tuple[int, int]]]   # OR of groups, each an AND of (byte position on the line, value)


class UtsClient(ABC):
    @abstractmethod
    def post(self, path: str, interface: int, body: dict) -> None:
        """Sends one item on the given bus + interface (HTTP POST)."""

    @abstractmethod
    def get(self, path: str, interface: int) -> list[dict]:
        """Returns the items received since the last call (HTTP GET)."""

    # ---------------------------------------------------------------- management (optional)
    # Not abstract: a client without them keeps working; only these calls raise NotImplementedError.

    def get_config(self, path: str, interface: int) -> dict:
        """Settings of an interface (HTTP GET configs)."""
        raise NotImplementedError

    def set_config(self, path: str, interface: int, settings: dict) -> None:
        """Writes settings of an interface (HTTP POST configs)."""
        raise NotImplementedError

    def get_filter(self, path: str, interface: int) -> tuple[str, FilterGroups]:
        """Receive filter of an interface as (kind, groups); kind "NONE": no filter.
        The client converts the UTS answer into this form, so it can be changed and written back."""
        raise NotImplementedError

    def set_filter(self, path: str, interface: int, kind: str, groups: FilterGroups) -> None:
        """kind: "INCLUSIVE" (only the groups pass) or "NONE" (no filter)."""
        raise NotImplementedError
