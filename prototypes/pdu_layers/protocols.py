"""Protocol layer: knows the PCI of one bus type, nothing about the gateway (UTS).

A protocol
- defines its PCI type: the address fields a message must give when it is created
- checks the PCI and the SDU against the rules of the bus (ranges, sizes)
- for byte streams: puts an in-band header (PCI as bytes) in front of the SDU and reads it back

One protocol object belongs to one channel, so two channels of the same bus type can be configured
differently (e.g. one Ethernet interface with a header, one without).
"""
import struct
from typing import Optional

from .pdu import CanPci, FramedPci, Mil1553Pci, NoPci, Pci, Pdu


class Protocol:
    path = ""                       # bus name in the gateway's URL ("ethernet", "serials", "1553", "can")
    pci_type: type[Pci] = NoPci

    def make_pci(self, **address) -> Pci:
        """PCI of a message from the address given at creation. A missing field raises TypeError."""
        missing = [n for n in self.pci_type.names() if n not in address]
        if missing:
            raise TypeError(f"{type(self).__name__}: a message needs {', '.join(missing)}")
        pci = self.pci_type(**address)
        self.check_pci(pci)
        return pci

    def check_pci(self, pci: Pci) -> None:
        pass

    def check_sdu(self, sdu: bytes) -> None:
        pass


# ---------------------------------------------------------------- byte streams (RS422, Ethernet, UART)

class Header:
    """In-band PCI on a byte stream: written in front of the SDU, read back on receive."""
    pci_type: type[Pci] = NoPci

    def encode(self, pdu: Pdu) -> bytes:
        raise NotImplementedError

    def decode(self, data: bytes, timestamp: Optional[float]) -> Optional[Pdu]:
        """The PDU, or None if the bytes do not belong to this header (the next channel is tried)."""
        raise NotImplementedError


class DeviceHeader(Header):
    """Example header: A5 | device | SDU length | SDU."""
    pci_type = FramedPci
    SYNC = 0xA5

    def encode(self, pdu: Pdu) -> bytes:
        return bytes([self.SYNC, pdu.pci.device, len(pdu.sdu)]) + pdu.sdu

    def decode(self, data: bytes, timestamp: Optional[float]) -> Optional[Pdu]:
        if len(data) < 3 or data[0] != self.SYNC or data[2] != len(data) - 3:
            return None
        return Pdu(FramedPci(data[1]), data[3:], timestamp)


class ByteStream(Protocol):
    """RS422 / Ethernet: no PCI unless a header is given."""

    def __init__(self, path: str, header: Optional[Header] = None):
        self.path = path
        self.header = header
        self.pci_type = header.pci_type if header else NoPci

    def to_bytes(self, pdu: Pdu) -> bytes:
        return self.header.encode(pdu) if self.header else pdu.sdu

    def from_bytes(self, data: bytes, timestamp: Optional[float]) -> Optional[Pdu]:
        if self.header is None:
            return Pdu(NoPci(), data, timestamp)
        return self.header.decode(data, timestamp)


def Ethernet(header: Optional[Header] = None) -> ByteStream:
    return ByteStream("ethernet", header)


def Rs422(header: Optional[Header] = None) -> ByteStream:
    return ByteStream("serials", header)


# ---------------------------------------------------------------- MIL-STD-1553

class Mil1553(Protocol):
    path = "1553"
    pci_type = Mil1553Pci
    NODES = range(1, 33)            # numbering as given for the UTS (1..32)
    SUBNETS = range(1, 33)
    MAX_WORDS = 32

    def check_pci(self, pci: Mil1553Pci) -> None:
        if pci.node not in self.NODES or pci.subnet not in self.SUBNETS:
            raise ValueError(f"1553: node {pci.node} / subnet {pci.subnet} out of range 1..32")

    def check_sdu(self, sdu: bytes) -> None:
        if len(sdu) % 2 or not 0 < len(sdu) // 2 <= self.MAX_WORDS:
            raise ValueError(f"1553: {len(sdu)} bytes is not 1..{self.MAX_WORDS} 16-bit words")

    @staticmethod
    def to_words(sdu: bytes) -> list[int]:
        return list(struct.unpack(f">{len(sdu) // 2}H", sdu))     # words are sent MSB first

    @staticmethod
    def from_words(words: list[int]) -> bytes:
        return struct.pack(f">{len(words)}H", *words)


# ---------------------------------------------------------------- CAN

class Can(Protocol):
    path = "can"
    pci_type = CanPci

    def check_pci(self, pci: CanPci) -> None:
        if not 0 <= pci.can_id < 0x800:
            raise ValueError(f"CAN: id 0x{pci.can_id:X} is not an 11-bit id")

    def check_sdu(self, sdu: bytes) -> None:
        if len(sdu) > 8:
            raise ValueError(f"CAN: {len(sdu)} bytes, at most 8")
