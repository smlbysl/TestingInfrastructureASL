"""Protocol: how the bytes of one bus type are written to and read from UTS.

    encode(data)          TX: bytes on the line -> body of the UTS POST
    decode(item)          RX: one item of the UTS GET -> Received(bytes, time)
    simulate(data, ts)    the item UTS would return (used by FakeUtsClient)

A protocol sees only the bytes on the line; envelope, splitter, signature and timing stay in the core.
"""

__author__ = "İsmail Baysal"

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Received:
    data: bytes                         # bytes on the line
    timestamp: Optional[float]          # UTS time in seconds


class Protocol(ABC):
    path: str = ""                      # bus name in the UTS URL: /{path}/{interface}/messages

    @abstractmethod
    def encode(self, data: bytes) -> dict:
        """Bytes on the line -> UTS request body."""

    @abstractmethod
    def decode(self, item: dict) -> Received:
        """One UTS item -> bytes and time."""

    def simulate(self, data: bytes, timestamp: Optional[float]) -> dict:
        """UTS item for data, as if the device had sent it."""
        raise NotImplementedError(f"{type(self).__name__} cannot be simulated")
