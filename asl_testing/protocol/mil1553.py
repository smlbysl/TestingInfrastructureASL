"""MIL-STD-1553: the PCI is node + subnet (remote terminal address + subaddress); the data are 16-bit words.

    class MyChannels(ChannelSet):
        BUS_A = Mil1553Channel(1)

    report = bit_report(node=5, subnet=3)       # node and subnet are mandatory

The SDU is the message bytes; the protocol turns them into words in `byteorder` (default: big, so a
BigEndianStructure message maps one c_uint16 field to one word). The word count comes from the size.
Open points: whether the T/R bit and mode codes belong to the PCI; the UTS numbering (1..32 is used).
"""
import struct

from dataclasses import dataclass

from asl_testing.protocol.base import Protocol
from asl_testing.protocol.pdu import Pci


@dataclass(frozen=True)
class Mil1553Pci(Pci):
    node: int                       # remote terminal address
    subnet: int                     # subaddress


class Mil1553(Protocol):
    path = "1553"
    pci_type = Mil1553Pci
    NODES = range(1, 33)            # numbering of the UTS (1..32)
    SUBNETS = range(1, 33)
    MAX_WORDS = 32

    def __init__(self, byteorder: str = "big"):
        if byteorder not in ("big", "little"):
            raise ValueError("byteorder is 'big' or 'little'")
        self.byteorder = byteorder
        self._fmt = ">" if byteorder == "big" else "<"

    def check_pci(self, pci: Mil1553Pci) -> None:
        if pci.node not in self.NODES or pci.subnet not in self.SUBNETS:
            raise ValueError(f"1553: node {pci.node} / subnet {pci.subnet} out of range "
                             f"{self.NODES.start}..{self.NODES.stop - 1}")

    def check_sdu(self, sdu: bytes) -> None:
        if len(sdu) % 2 or not 0 < len(sdu) // 2 <= self.MAX_WORDS:
            raise ValueError(f"1553: {len(sdu)} bytes is not 1..{self.MAX_WORDS} 16-bit words")

    def to_words(self, sdu: bytes) -> list[int]:
        return list(struct.unpack(f"{self._fmt}{len(sdu) // 2}H", sdu))

    def from_words(self, words: list[int]) -> bytes:
        return struct.pack(f"{self._fmt}{len(words)}H", *words)
