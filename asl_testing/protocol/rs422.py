"""RS422 protocol.

    POST body : {"message": [b0, b1, ...]}
    GET item  : {"message": [b0, b1, ...], "timestamp": t}

Same format as Ethernet today, kept as a separate class so the two can change independently.
A GET item may hold part of a stream; the channel's splitter cuts it into packets after decode.
To check with the real UTS: field names and timestamp unit (time_unit = seconds per UTS unit).
"""

__author__ = "İsmail Baysal"

from typing import Optional

from asl_testing.protocol.base import Protocol, Received


class Rs422Protocol(Protocol):
    path = "rs422"

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
