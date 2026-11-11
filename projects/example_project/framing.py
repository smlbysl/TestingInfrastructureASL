"""Framing of the project.

EthHeader: example 8-byte header in front of every message on a channel, outside the message's
length and checksum. Layout: 55 AA | total length (uint16 LE) | 4 reserved bytes.
"""

__author__ = "İsmail Baysal"
import struct
from typing import Optional

from asl_testing import Envelope


class EthHeader(Envelope):
    MAGIC = b"\x55\xAA"
    SIZE = 8
    offset = SIZE                                       # the message starts after the header

    def on_send(self, data: bytes) -> bytes:
        return self.MAGIC + struct.pack("<H", self.SIZE + len(data)) + bytes(4) + data

    def on_receive(self, wire: bytes) -> Optional[bytes]:
        if len(wire) < self.SIZE or wire[:2] != self.MAGIC:
            return None
        if struct.unpack_from("<H", wire, 2)[0] != len(wire):
            return None
        return wire[self.SIZE:]
