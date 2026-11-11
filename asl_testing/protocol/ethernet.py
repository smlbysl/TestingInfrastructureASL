"""Ethernet protocol.

    POST body : {"message": [b0, b1, ...]}
    GET item  : {"message": [b0, b1, ...], "timestamp": t}

To check with the real UTS: field names and timestamp unit (time_unit = seconds per UTS unit).
"""

__author__ = "İsmail Baysal"

from typing import Optional

from asl_testing.protocol.base import Protocol, Received


class EthernetProtocol(Protocol):
    path = "ethernet"

    def __init__(self, time_unit: float = 1.0):
        self.time_unit = time_unit

    def encode(self, data: bytes) -> dict:
        return {"message": list(data)}

    def decode(self, item: dict) -> Received:
        timestamp = item.get("timestamp")
        return Received(bytes(item["message"]), None if timestamp is None else timestamp * self.time_unit)

    def simulate(self, data: bytes, timestamp: Optional[float]) -> dict:
        item = {"message": list(data)}
        if timestamp is not None:
            item["timestamp"] = timestamp / self.time_unit
        return item
