"""Protocol: the contract between the core and one bus type.

The core does not know how a protocol works inside. It gives the protocol the bytes to send and gets
back the UTS request body; it gives the protocol an item UTS returned and gets back the bytes received.

    TX:  encode(data)    -> body for UTS (POST on path / interface)
    RX:  decode(item)    -> Received(data, timestamp)
    simulate(data, ts)   -> the item UTS would return (only for the fake UTS in tests)

Step 1 (Ethernet): bytes only. Addresses (1553 node / subnet, CAN id) and protocol settings come in
later steps, when a protocol needs them.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Received:
    data: bytes                         # the bytes on the line (header included, as before)
    timestamp: Optional[float]          # UTS arrival time in seconds


class Protocol(ABC):
    path: str = ""                      # bus name in the UTS URL: /{path}/{interface}/messages

    @abstractmethod
    def encode(self, data: bytes) -> dict:
        """TX: bytes on the line -> the UTS request body."""

    @abstractmethod
    def decode(self, item: dict) -> Received:
        """RX: one item of the UTS answer -> the bytes received and their time."""

    def simulate(self, data: bytes, timestamp: Optional[float]) -> dict:
        """The item UTS would return if the device sent data (for the fake UTS). Optional."""
        raise NotImplementedError(f"{type(self).__name__} cannot be simulated")
