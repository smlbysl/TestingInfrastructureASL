"""UtsClient: what the framework needs from UTS. Everything UTS-specific stays in comm/uts."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from comm.link import Link


class UtsError(Exception):
    """A UTS request failed (HTTP error, statusInfo not OK, UTS unreachable)."""


@dataclass(frozen=True)
class UtsFrame:
    data: bytes
    timestamp: Optional[float]          # UTS arrival time in seconds


@dataclass(frozen=True)
class UtsFetch:
    frames: list[UtsFrame]
    overflow: bool                      # UTS buffer overflowed: packets were lost


FilterGroups = list[list[tuple[int, int]]]  # OR of groups, each an AND of (byte position, value)


class UtsClient(ABC):
    @abstractmethod
    def read_config(self, link: Link) -> tuple[dict[str, Any], dict[str, Any]]:
        """Returns (settings, device status) of an interface."""

    @abstractmethod
    def write_config(self, link: Link) -> None:
        """Writes the link settings to UTS."""

    @abstractmethod
    def transfer(self, link: Link, data: bytes) -> None:
        """Sends bytes on an interface."""

    @abstractmethod
    def fetch(self, link: Link) -> UtsFetch:
        """Returns the packets buffered on an interface; UTS empties its buffer."""

    @abstractmethod
    def write_filter(self, link: Link, kind: str, groups: FilterGroups) -> None:
        """kind: "INCLUSIVE" or "NONE"."""

    def clear(self, link: Link) -> None:
        """Empties the UTS receive buffer of an interface (a fetch whose packets are dropped)."""
        self.fetch(link)
