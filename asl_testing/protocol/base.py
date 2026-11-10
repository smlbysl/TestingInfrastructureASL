"""Protocol: one bus type - its PCI, its rules and how it recognises its packets. Nothing about UTS.

A protocol object belongs to one channel, so two channels of the same bus type can be set up
differently (e.g. one Ethernet interface with a header, one without).

The gateway adapter turns what UTS returns into "units" for the protocol: bytes for a byte stream,
a PDU for a bus whose PCI travels next to the data (1553, CAN). receive() turns a unit into this
channel's PDU, or returns None when the unit does not belong to the channel (the next one is tried).
"""
from typing import ClassVar, Optional

from asl_testing.protocol.pdu import NoPci, Pci, Pdu


class Protocol:
    path: ClassVar[str] = ""               # bus name in the gateway's URL ("ethernet", "serials", "1553", "can")
    pci_type: type[Pci] = NoPci
    offset: int = 0                         # bytes in front of the SDU on the line (UTS filter positions)

    @property
    def accepts_all(self) -> bool:
        """True if receive() never refuses a unit: such a channel is tried last on its address,
        and an address has at most one."""
        return True

    # ---------------------------------------------------------------- PCI and SDU rules

    def make_pci(self, **address) -> Pci:
        """PCI of a message from the address given at creation. A missing field raises TypeError,
        a value out of range ValueError (see check_pci)."""
        missing = [name for name in self.pci_type.names() if name not in address]
        if missing:
            raise TypeError(f"{type(self).__name__}: a message needs {', '.join(missing)}")
        extra = [name for name in address if name not in self.pci_type.names()]
        if extra:
            raise TypeError(f"{type(self).__name__}: unknown address field(s) {', '.join(extra)}")
        pci = self.pci_type(**address)
        self.check_pci(pci)
        return pci

    def check_pci(self, pci: Pci) -> None:
        """Raises ValueError if the PCI breaks a rule of the bus (ranges)."""

    def check_sdu(self, sdu: bytes) -> None:
        """Raises ValueError if the SDU cannot be sent on the bus (size, word alignment). Called on TX."""

    # ---------------------------------------------------------------- PDU <-> line

    def wire(self, pdu: Pdu) -> bytes:
        """The PDU as bytes on the line (for logs and line-level events). Default: the SDU."""
        return pdu.sdu

    def receive(self, unit, timestamp: Optional[float]) -> Optional[Pdu]:
        """This channel's PDU from a unit of the adapter, or None if it does not belong here."""
        return unit if isinstance(unit, Pdu) else None

    def __repr__(self) -> str:
        return type(self).__name__
