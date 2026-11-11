"""UtsClient: how UTS is reached (UTS is an HTTP service).

An interface is addressed by the protocol's path and the interface number:
POST sends on it; GET returns what was received there and empties the buffer. The body and the
items are built and read by the channel's protocol object; the client passes them as they are.

Open until the UTS API is available: JSON layout of GET, timestamp unit, body of config and filter
calls (master: {"type": kind, "filter": [[{"filterBytePos", "filterValue"}]]}).
"""

__author__ = "İsmail Baysal"

from abc import ABC, abstractmethod


class UtsError(Exception):
    """A UTS request failed (HTTP error, status not OK, UTS unreachable)."""


FilterGroups = list[list[tuple[int, int]]]   # OR of groups; a group is an AND of (byte position, value)


class UtsClient(ABC):
    @abstractmethod
    def post(self, path: str, interface: int, body: dict) -> None:
        """POST /{path}/{interface}/messages with the body from the protocol."""

    @abstractmethod
    def get(self, path: str, interface: int) -> list[dict]:
        """GET /{path}/{interface}/messages: items received since the last call."""

    # ---------------------------------------------------------------- management (optional)

    def get_config(self, path: str, interface: int) -> dict:
        """Settings of an interface."""
        raise NotImplementedError

    def set_config(self, path: str, interface: int, settings: dict) -> None:
        """Writes settings of an interface."""
        raise NotImplementedError

    def get_filter(self, path: str, interface: int) -> tuple[str, FilterGroups]:
        """Receive filter as (kind, groups); kind "NONE" means no filter."""
        raise NotImplementedError

    def set_filter(self, path: str, interface: int, kind: str, groups: FilterGroups) -> None:
        """kind "INCLUSIVE": only the groups pass; "NONE": no filter."""
        raise NotImplementedError
