"""Adapter: what the core needs from the system between the test PC and the device.

    send(channel, wire)     sends the bytes on the line of a channel
    receive(channel)        what the channel's interface received since the last call: list of Received

Config and filters are optional; an adapter without them raises AdapterError("... not supported").
The target of those calls is a channel or a message (its channel).
UtsAdapter (adapter/uts) is the adapter of UTS; another system gets its own adapter.
"""

__author__ = "İsmail Baysal"

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Received:
    data: bytes                         # bytes on the line
    timestamp: Optional[float]          # time of the adapter (UTS) in seconds


class AdapterError(Exception):
    """A request of the adapter failed (error answer, not reachable, no answer within the timeout)."""


FilterGroups = list[list[tuple[int, int]]]   # OR of groups; a group is an AND of (byte position, value)


class Adapter(ABC):
    @abstractmethod
    def send(self, channel, wire: bytes) -> None:
        """Sends the bytes on the line of a channel; AdapterError if it fails."""

    @abstractmethod
    def receive(self, channel) -> list[Received]:
        """What the channel's interface received since the last call; AdapterError if it fails."""

    # ---------------------------------------------------------------- config and filters (optional)

    def get_config(self, target) -> dict[str, Any]:
        raise AdapterError(f"{type(self).__name__}: config not supported")

    def set_config(self, target, **settings) -> None:
        raise AdapterError(f"{type(self).__name__}: config not supported")

    def get_filter(self, target) -> tuple[str, FilterGroups]:
        raise AdapterError(f"{type(self).__name__}: filters not supported")

    def set_filter(self, target, groups: FilterGroups, kind: str = "INCLUSIVE") -> None:
        raise AdapterError(f"{type(self).__name__}: filters not supported")

    def clear_filter(self, target) -> None:
        raise AdapterError(f"{type(self).__name__}: filters not supported")

    def add_filter(self, msg) -> None:
        raise AdapterError(f"{type(self).__name__}: filters not supported")

    def remove_filter(self, msg) -> None:
        raise AdapterError(f"{type(self).__name__}: filters not supported")
