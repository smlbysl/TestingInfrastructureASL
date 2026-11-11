"""Protocol: the contract between the core and one bus type.

The core does not know how a protocol works inside. It gives the protocol the bytes to send and gets
back the UTS request body; it gives the protocol an item UTS returned and gets back the bytes received.

    TX:  encode(data, address)    -> body for UTS (POST on path / interface)
    RX:  decode(item)             -> Received(data, timestamp, address)
    simulate(data, ts, address)   -> the item UTS would return (only for the fake UTS in tests)

address: the protocol's own address of a packet on the interface (1553: remote terminal + subaddress,
CAN: identifier). A protocol without addresses (Ethernet, RS422) ignores it and returns None.
Its type belongs to the protocol; the core only passes it on.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Received:
    data: bytes                         # the bytes on the line (header included, as before)
    timestamp: Optional[float]          # UTS arrival time in seconds
    address: Any = None                 # the protocol's address of the packet (None: no addresses)


class Protocol(ABC):
    path: str = ""                      # bus name in the UTS URL: /{path}/{interface}/messages

    @abstractmethod
    def encode(self, data: bytes, address: Any = None) -> dict:
        """TX: bytes on the line (and the packet's address, if the protocol has addresses) -> UTS request body."""

    @abstractmethod
    def decode(self, item: dict) -> Received:
        """RX: one item of the UTS answer -> the bytes received, their time and address.
        Raises ValueError for an item that does not follow the protocol's format."""

    def simulate(self, data: bytes, timestamp: Optional[float], address: Any = None) -> dict:
        """The item UTS would return if the device sent data (for the fake UTS). Optional."""
        raise NotImplementedError(f"{type(self).__name__} cannot be simulated")
