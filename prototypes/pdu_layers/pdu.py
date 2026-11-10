"""PDU model: PDU = PCI + SDU (the AUTOSAR naming).

SDU : service data unit - the payload one layer receives from the layer above (here: the message bytes).
PCI : protocol control information - the fields a protocol adds on its own (1553 node/subnet, CAN id ...).
PDU : protocol data unit - PCI + SDU, what a protocol layer hands to the layer below (or receives from it).

A PCI type is a frozen dataclass: its fields are the address of a message on that protocol, and the
channel registry finds the candidate messages of an incoming PDU by pci.key().
"""
from dataclasses import dataclass, fields
from typing import Optional


@dataclass(frozen=True)
class Pci:
    """Base of every PCI type: no fields, so every PDU of the protocol has the same key."""

    def key(self) -> tuple:
        return tuple(getattr(self, f.name) for f in fields(self))

    @classmethod
    def names(cls) -> tuple[str, ...]:
        """Names of the fields a message must give when it is created."""
        return tuple(f.name for f in fields(cls))


@dataclass(frozen=True)
class NoPci(Pci):
    """Plain RS422 / Ethernet: the payload goes as it is, the protocol adds nothing."""


@dataclass(frozen=True)
class FramedPci(Pci):
    """A header on a byte stream that carries an address (example: a device number)."""
    device: int


@dataclass(frozen=True)
class Mil1553Pci(Pci):
    node: int                       # remote terminal address
    subnet: int                     # subaddress


@dataclass(frozen=True)
class CanPci(Pci):
    can_id: int


@dataclass(frozen=True)
class Pdu:
    pci: Pci
    sdu: bytes
    timestamp: Optional[float] = None    # seconds, from the gateway (UTS); None on TX
