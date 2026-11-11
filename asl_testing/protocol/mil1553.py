"""MIL-STD-1553 protocol: a packet is a list of 16-bit values.

    POST body : {"message": [rt, subnet, word_count, word, word, ...]}
    GET item  : {"message": [rt, subnet, word_count, word, word, ...], "timestamp": t}
    example   : rt 30, subnet 1, 3 data words -> [30, 1, 3, 0x0001, 0x3344, 0x1122]

rt, subnet and word_count are the first fields of the message (c_uint16 in the project), so this
class only converts the message bytes to that list and back. Values are not checked.

byte_order must match the byte order of the message structures:

    structure               byte_order   list              32-bit field
    LittleEndianStructure   "little"     [30, 1, ...]      2 words, low word first
    BigEndianStructure      "big"        [30, 1, ...]      2 words, high word first
    mismatch                             [7680, 256, ...]  bytes of every value swapped

To check with the real UTS: field names and timestamp unit (time_unit = seconds per UTS unit).
"""

__author__ = "İsmail Baysal"

from typing import Optional

from asl_testing.protocol.base import Protocol, Received


class Mil1553Protocol(Protocol):
    path = "mil1553"

    def __init__(self, byte_order: str = "little", time_unit: float = 1.0):
        self.byte_order = byte_order                    # "little" or "big"
        self.time_unit = time_unit

    def encode(self, data: bytes) -> dict:
        return {"message": self.to_words(data)}

    def decode(self, item: dict) -> Received:
        timestamp = item.get("timestamp")
        return Received(self.to_bytes(item["message"]), None if timestamp is None else timestamp * self.time_unit)

    def simulate(self, data: bytes, timestamp: Optional[float]) -> dict:
        item = self.encode(data)
        if timestamp is not None:
            item["timestamp"] = timestamp / self.time_unit
        return item

    def to_words(self, data: bytes) -> list[int]:
        return [int.from_bytes(data[i:i + 2], self.byte_order) for i in range(0, len(data), 2)]

    def to_bytes(self, words: list[int]) -> bytes:
        return b"".join(word.to_bytes(2, self.byte_order) for word in words)
