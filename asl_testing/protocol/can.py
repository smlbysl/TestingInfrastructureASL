"""CAN: the PCI is the CAN id; the data are 0..8 bytes (classic CAN).

    class MyChannels(ChannelSet):
        CAN0 = CanChannel(0)

    class wheel_speed(CanBase):
        _address = {"can_id": 0x123}            # class default; or wheel_speed(can_id=0x123)

A signature inside the data is still possible (several messages under one id).
Open points: CAN FD (64 bytes), remote frames.
"""
from dataclasses import dataclass

from asl_testing.protocol.base import Protocol
from asl_testing.protocol.pdu import Pci


@dataclass(frozen=True)
class CanPci(Pci):
    can_id: int


class Can(Protocol):
    path = "can"
    pci_type = CanPci
    MAX_BYTES = 8

    def __init__(self, extended: bool = False):
        self.extended = extended                # 29-bit ids instead of 11-bit

    def check_pci(self, pci: CanPci) -> None:
        bits = 29 if self.extended else 11
        if not 0 <= pci.can_id < (1 << bits):
            raise ValueError(f"CAN: id 0x{pci.can_id:X} does not fit in {bits} bits")

    def check_sdu(self, sdu: bytes) -> None:
        if len(sdu) > self.MAX_BYTES:
            raise ValueError(f"CAN: {len(sdu)} bytes, at most {self.MAX_BYTES}")
