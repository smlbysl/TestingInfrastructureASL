"""PDU model: PDU = PCI + SDU (the AUTOSAR naming).

SDU : service data unit - what a layer receives from the layer above; here the message bytes.
PCI : protocol control information - the fields a protocol adds on its own (1553 node / subnet,
      CAN id, an in-band header ...). It is the address of a message on that protocol.
PDU : protocol data unit - PCI + SDU, what the protocol layer hands to the gateway adapter (TX)
      or receives from it (RX).

A PCI type is a frozen dataclass. Its fields are mandatory when a message is created on a channel of
that protocol, and the channel registry finds the candidate messages of an incoming PDU by pci.key().
"""
from dataclasses import dataclass, fields
from typing import Optional


@dataclass(frozen=True)
class Pci:
    """Base of every PCI type."""

    def key(self) -> tuple:
        return tuple(getattr(self, f.name) for f in fields(self))

    @classmethod
    def names(cls) -> tuple[str, ...]:
        """Field names: a message created on this protocol must give them (keyword or _address)."""
        return tuple(f.name for f in fields(cls))

    def __str__(self) -> str:
        return " ".join(f"{f.name}={getattr(self, f.name)}" for f in fields(self))


@dataclass(frozen=True)
class NoPci(Pci):
    """A protocol that adds no fields (plain Ethernet / RS422): every PDU has the same, empty key."""


NO_PCI = NoPci()


@dataclass(frozen=True)
class Pdu:
    pci: Pci
    sdu: bytes
    timestamp: Optional[float] = None    # seconds, from the gateway (UTS); None on TX
