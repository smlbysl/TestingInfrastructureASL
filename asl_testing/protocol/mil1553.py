"""MIL-STD-1553: UTS carries a packet as one list of numbers.

    POST body : {"message": [rt, subaddress, word_count, w0, w1, ...]}
    GET item  : {"message": [rt, subaddress, word_count, w0, w1, ...], "timestamp": t}

- rt, subaddress: the packet's address on the bus, each 1..32 (Mil1553Address)
- word_count: number of data words that follow, 1..32
- w0, w1 ...: 16-bit data words

The core works with bytes (the ctypes layout of the message); this class turns them into 16-bit words
and back. How two bytes form one word is set by byte_order and must match the byte order of the
project's message structures:

    message structure       byte_order   result
    LittleEndianStructure   "little"     16-bit fields = one word each; a 32-bit field = 2 words, low word first
    BigEndianStructure      "big"        16-bit fields = one word each; a 32-bit field = 2 words, high word first
    any other combination                every word has its two bytes swapped (wrong on the bus)

A 32-bit field is always 2 words here (not 4 bytes). Which word comes first follows the structure's byte
order, so if the ICD wants the high word first, the project uses BigEndianStructure (and byte_order="big").
Note K3 in docs/KNOWN_ISSUES.md: special field types (length, CRC ...) do not follow BigEndianStructure yet.

To be checked against the real UTS: the field names, whether word_count 32 is sent as 32 or as 0
(1553 command word), the address ranges and the unit of the timestamp.
"""
from dataclasses import dataclass
from typing import Any, Optional

from asl_testing.protocol.base import Protocol, Received

ADDRESS_RANGE = range(1, 33)            # rt and subaddress: 1..32
MAX_WORDS = 32


@dataclass(frozen=True)
class Mil1553Address:
    """Address of a packet on a 1553 bus. Checked when it is created."""
    rt: int                             # remote terminal address
    subaddress: int

    def __post_init__(self):
        for name in ("rt", "subaddress"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value not in ADDRESS_RANGE:
                raise ValueError(f"1553 {name} must be an integer in 1..32, got {value!r}")

    def __str__(self) -> str:
        return f"RT{self.rt}/SA{self.subaddress}"


class Mil1553Protocol(Protocol):
    path = "mil1553"

    def __init__(self, byte_order: str = "little", time_unit: float = 1.0):
        if byte_order not in ("little", "big"):
            raise ValueError('byte_order must be "little" or "big"')
        self.byte_order = byte_order    # how two bytes form one 16-bit word (see the module text)
        self.time_unit = time_unit      # seconds per UTS timestamp unit

    # ---------------------------------------------------------------- bytes <-> words

    def to_words(self, data: bytes) -> list[int]:
        if len(data) % 2:
            raise ValueError(f"1553 data is 16-bit words: {len(data)} bytes is not a whole number of words")
        words = [int.from_bytes(data[i:i + 2], self.byte_order) for i in range(0, len(data), 2)]
        if not 1 <= len(words) <= MAX_WORDS:
            raise ValueError(f"1553 packet must have 1..{MAX_WORDS} data words, got {len(words)}")
        return words

    def to_bytes(self, words: list[int]) -> bytes:
        for word in words:
            if isinstance(word, bool) or not isinstance(word, int) or not 0 <= word <= 0xFFFF:
                raise ValueError(f"1553 data word must be 0..0xFFFF, got {word!r}")
        return b"".join(word.to_bytes(2, self.byte_order) for word in words)

    # ---------------------------------------------------------------- contract

    def encode(self, data: bytes, address: Any = None) -> dict:
        if not isinstance(address, Mil1553Address):
            raise ValueError(f"1553 needs a Mil1553Address to send, got {address!r}")
        words = self.to_words(data)
        return {"message": [address.rt, address.subaddress, len(words), *words]}

    def decode(self, item: dict) -> Received:
        values = item.get("message")
        if not isinstance(values, list) or len(values) < 3:
            raise ValueError(f"1553 item needs [rt, subaddress, word_count, words...], got {values!r}")
        rt, subaddress, count, *words = values
        address = Mil1553Address(rt, subaddress)
        if count != len(words):
            raise ValueError(f"1553 item at {address}: word_count {count} but {len(words)} words")
        timestamp = item.get("timestamp")
        return Received(self.to_bytes(words), None if timestamp is None else timestamp * self.time_unit, address)

    def simulate(self, data: bytes, timestamp: Optional[float], address: Any = None) -> dict:
        item = self.encode(data, address)
        if timestamp is not None:
            item["timestamp"] = timestamp / self.time_unit
        return item
