"""Project-specific framing.

EthHeader is an example header (in-band PCI of a byte stream): 8 bytes in front of every message on
a channel, computed from the length and not part of the message's length field or checksum.
It carries no address, so its PCI is NoPci. Layout: 55 AA | total length (uint16, little endian) | 4 reserved.
Replace it with the real header of the project.
"""
import struct
from typing import Optional

from asl_testing import NO_PCI, Header, Pci


class EthHeader(Header):
    MAGIC = b"\x55\xAA"
    SIZE = 8
    offset = SIZE                                       # the message starts after the header

    def encode(self, pci: Pci, sdu: bytes) -> bytes:
        return self.MAGIC + struct.pack("<H", self.SIZE + len(sdu)) + bytes(4) + sdu

    def decode(self, data: bytes) -> Optional[tuple[Pci, bytes]]:
        if len(data) < self.SIZE or data[:2] != self.MAGIC:
            return None                                 # not a packet of this channel
        if struct.unpack_from("<H", data, 2)[0] != len(data):
            return None
        return NO_PCI, data[self.SIZE:]
