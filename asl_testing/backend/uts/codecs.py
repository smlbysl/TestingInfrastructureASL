"""Codecs: the UTS JSON of each bus type.

    encode(channel, data)           TX: bytes on the line -> body of the UTS POST
    sent_time(body)                 TX: time in the answer of the POST, in seconds
    items(body), overflow(body)     RX: list of items and the overflow flag in the answer of the GET
    decode(channel, item)           RX: one item -> Received(bytes, time)
    simulate(channel, data, time)   the item UTS would return (used by FakeUtsBackend)

Answers (the same for every bus as far as known; the serial ones are documented):
    POST : {"statusInfo": {...}, "timestamp": t}
    GET  : {"statusInfo": {...}, "messages": [item, ...], "isBufferOverflow": false}
    t is in microseconds (time_unit = seconds per UTS unit, 1e-6).

Serial, Ethernet:
    POST body : {"message": [b0, b1, ...]}
    GET item  : {"message": [b0, b1, ...], "timestamp": t}
    A serial item may hold part of a stream; the channel's splitter cuts it into packets after decode.

MIL-STD-1553: a packet is a list of 16-bit values.
    POST body : {"message": [rt, subnet, word_count, word, word, ...]}
    GET item  : {"message": [rt, subnet, word_count, word, word, ...], "timestamp": t}
    example   : rt 30, subnet 1, 3 data words -> [30, 1, 3, 0x0001, 0x3344, 0x1122]

    rt, subnet and word_count are the first fields of the message (c_uint16 in the project), so the
    codec only converts the message bytes to that list and back. Values are not checked.
    The channel's byte_order must match the byte order of the message structures:

    structure               byte_order   list              32-bit field
    LittleEndianStructure   "little"     [30, 1, ...]      2 words, low word first
    BigEndianStructure      "big"        [30, 1, ...]      2 words, high word first
    mismatch                             [7680, 256, ...]  bytes of every value swapped

timeout is how long an answer of UTS is waited for: the TX timeout of UTS for the bus plus a margin
(UTS: 1 s for Ethernet and 1553; for serial it depends on the baud rate, at least 1 s).

To check with the real UTS: the answers of Ethernet and 1553, and that the timestamp is in microseconds.
"""

__author__ = "İsmail Baysal"

from typing import Optional

from asl_testing.backend.base import Received


class Codec:
    path: str = ""                      # root of the bus in the UTS URL
    timeout: float = 2.0                # seconds to wait for an answer of UTS

    def __init__(self, time_unit: float = 1e-6):
        self.time_unit = time_unit

    def encode(self, channel, data: bytes) -> dict:
        return {"message": self.to_list(channel, data)}

    def sent_time(self, body: Optional[dict]) -> Optional[float]:
        return self._seconds((body or {}).get("timestamp"))

    def items(self, body: Optional[dict]) -> list[dict]:
        return (body or {}).get("messages") or []

    def overflow(self, body: Optional[dict]) -> bool:
        return bool((body or {}).get("isBufferOverflow"))

    def decode(self, channel, item: dict) -> Received:
        return Received(self.to_bytes(channel, item["message"]), self._seconds(item.get("timestamp")))

    def simulate(self, channel, data: bytes, timestamp: Optional[float]) -> dict:
        item = self.encode(channel, data)
        if timestamp is not None:
            item["timestamp"] = self.uts_time(timestamp)
        return item

    def uts_time(self, seconds: float) -> int:
        return round(seconds / self.time_unit)

    def _seconds(self, timestamp) -> Optional[float]:
        return None if timestamp is None else timestamp * self.time_unit

    def to_list(self, channel, data: bytes) -> list[int]:
        return list(data)

    def to_bytes(self, channel, values: list[int]) -> bytes:
        return bytes(values)


class SerialCodec(Codec):
    path = "serials"
    timeout = 3.0


class EthernetCodec(Codec):
    path = "ethernet"


class Mil1553Codec(Codec):
    path = "1553"

    def to_list(self, channel, data: bytes) -> list[int]:
        return [int.from_bytes(data[i:i + 2], channel.byte_order) for i in range(0, len(data), 2)]

    def to_bytes(self, channel, values: list[int]) -> bytes:
        return b"".join(word.to_bytes(2, channel.byte_order) for word in values)
