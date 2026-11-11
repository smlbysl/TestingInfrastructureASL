"""Ethernet: UTS carries the bytes of a packet as a list of numbers.

    POST body : {"message": [b0, b1, ...]}
    GET item  : {"message": [b0, b1, ...], "timestamp": t}

To be checked against the real UTS: the exact field names and the unit of the timestamp
(time_unit = seconds per UTS unit; 1.0 means UTS already gives seconds).
"""
from typing import Any, Optional

from asl_testing.protocol.base import Protocol, Received


class EthernetProtocol(Protocol):
    path = "ethernet"

    def __init__(self, time_unit: float = 1.0):
        self.time_unit = time_unit

    def encode(self, data: bytes, address: Any = None) -> dict:
        return {"message": list(data)}

    def decode(self, item: dict) -> Received:
        timestamp = item.get("timestamp")
        return Received(bytes(item["message"]), None if timestamp is None else timestamp * self.time_unit)

    def simulate(self, data: bytes, timestamp: Optional[float], address: Any = None) -> dict:
        item = {"message": list(data)}
        if timestamp is not None:
            item["timestamp"] = timestamp / self.time_unit
        return item
