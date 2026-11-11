"""MIL-STD-1553: UTS carries a packet as one list of 16-bit values.

    POST body : {"message": [rt, subnet, word_count, word, word, ...]}
    GET item  : {"message": [rt, subnet, word_count, word, word, ...], "timestamp": t}

    e.g. rt 30, subnet 1, 3 data words:  [30, 1, 3, 0x0001, 0x3344, 0x1122]

rt, subnet and word_count are fields of the message (defined by the project as c_uint16, first in the
structure), so the whole packet is a run of 16-bit values: this class only turns the message bytes into
that list and back. The values are not checked here; they come from the message definition and the test.

byte_order says how two bytes form one value and must match the byte order of the project's message
structures:

    message structure       byte_order   [rt=30, subnet=1, ...]   a 32-bit field
    LittleEndianStructure   "little"     [30, 1, ...]             2 words, low word first
    BigEndianStructure      "big"        [30, 1, ...]             2 words, high word first
    any other combination                [7680, 256, ...]         every value has its bytes swapped

A field narrower than 16 bits (e.g. rt as c_uint8) would share a value with its neighbour: define rt,
subnet and word_count as c_uint16.

To be checked against the real UTS: the field names and the unit of the timestamp
(time_unit = seconds per UTS unit; 1.0 means UTS already gives seconds).
"""
from typing import Optional

from asl_testing.protocol.base import Protocol, Received


class Mil1553Protocol(Protocol):
    path = "mil1553"

    def __init__(self, byte_order: str = "little", time_unit: float = 1.0):
        if byte_order not in ("little", "big"):
            raise ValueError('byte_order must be "little" or "big"')
        self.byte_order = byte_order
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

    # ---------------------------------------------------------------- bytes <-> 16-bit values

    def to_words(self, data: bytes) -> list[int]:
        return [int.from_bytes(data[i:i + 2], self.byte_order) for i in range(0, len(data), 2)]

    def to_bytes(self, words: list[int]) -> bytes:
        return b"".join(word.to_bytes(2, self.byte_order) for word in words)
