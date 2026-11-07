"""Project-specific framing.

EthHeader is an example envelope: an 8-byte header in front of every message on a channel,
computed from the length and not part of the message's length field or checksum.
Layout of the example: 55 AA | total length (uint16, little endian) | 4 reserved bytes.
Replace it with the real header of the project.
"""
import struct
from typing import Optional

from asl_testing.channel.framing import Envelope


class EthHeader(Envelope):
    MAGIC = b"\x55\xAA"
    SIZE = 8
    offset = SIZE                                       # the message starts after the header

    def on_send(self, data: bytes) -> bytes:
        return self.MAGIC + struct.pack("<H", self.SIZE + len(data)) + bytes(4) + data

    def on_receive(self, wire: bytes) -> Optional[bytes]:
        if len(wire) < self.SIZE or wire[:2] != self.MAGIC:
            return None                                 # not a packet of this channel
        if struct.unpack_from("<H", wire, 2)[0] != len(wire):
            return None
        return wire[self.SIZE:]
