"""Byte streams (Ethernet, RS422, UART): the line carries bytes only.

- Header (packet level): an in-band PCI in front of the SDU, e.g. a project's Ethernet header.
  It is written on TX and checked on RX; decode() returns None for a packet that is not this
  channel's, so the next channel on the same address is tried. Without a header the SDU goes as it is.
- Splitter (stream level): turns what UTS returned for an address into packets. It works before a
  packet is matched to a channel, so an address has at most one splitter.

    class MyChannels(ChannelSet):
        CONTROL = Rs422Channel(0)
        DIAG    = EthernetChannel(1, header=EthHeader())
        RAW     = EthernetChannel(1)
"""
from typing import Optional

from asl_testing.protocol.base import Protocol
from asl_testing.protocol.pdu import NO_PCI, NoPci, Pci, Pdu


class Header:
    """In-band PCI of a byte stream. A header without address fields uses NoPci (pci_type)."""
    pci_type: type[Pci] = NoPci
    offset = 0                              # header size: bytes in front of the SDU on the line

    def encode(self, pci: Pci, sdu: bytes) -> bytes:
        """TX: header + SDU."""
        raise NotImplementedError

    def decode(self, data: bytes) -> Optional[tuple[Pci, bytes]]:
        """RX: (PCI, SDU), or None when the packet does not belong to this header."""
        raise NotImplementedError


class Splitter:
    def split(self, data: bytes) -> list[bytes]:
        """Returns the packets contained in data. Default: data is one packet."""
        return [data]

    def reset(self) -> None:
        """Drops any partial packet kept between two reads."""


class ByteStream(Protocol):
    def __init__(self, header: Optional[Header] = None, splitter: Optional[Splitter] = None):
        self.header = header
        self.splitter = splitter
        if header is not None:
            self.pci_type = header.pci_type
            self.offset = header.offset

    @property
    def has_header(self) -> bool:
        return self.header is not None

    @property
    def has_splitter(self) -> bool:
        return self.splitter is not None

    @property
    def accepts_all(self) -> bool:
        return self.header is None

    def wire(self, pdu: Pdu) -> bytes:
        return self.header.encode(pdu.pci, pdu.sdu) if self.header is not None else pdu.sdu

    def receive(self, unit: bytes, timestamp: Optional[float]) -> Optional[Pdu]:
        if self.header is None:
            return Pdu(NO_PCI, unit, timestamp)
        found = self.header.decode(unit)
        return None if found is None else Pdu(found[0], found[1], timestamp)


class Ethernet(ByteStream):
    path = "ethernet"


class Serial(ByteStream):
    """Serial lines of the gateway (RS422 today; the serial mode is a channel setting)."""
    path = "serials"
