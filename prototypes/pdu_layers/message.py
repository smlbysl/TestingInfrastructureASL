"""Message layer: the SDU as a ctypes structure (the same idea as BaseMessageStructure, cut down).

    class bit_report(BeMessage):
        _channel = Ch.BUS_A
        _fields_ = [("status", c_uint16), ("temp", c_int16)]

    report = bit_report(node=5, subnet=3)            # PCI fields are mandatory: the protocol asks for them
    report.status                                     # field values as before

The message does not know the protocol's fields: it hands the address to its channel's protocol, which
builds the PCI. _signature (optional) tells messages apart under the same PCI: {field: value}.
"""
import ctypes
from typing import Optional

from .pdu import Pdu


class Message:
    """Mixin: combine with LittleEndianStructure or BigEndianStructure (see LeMessage / BeMessage)."""
    _pack_ = 1
    _channel = None
    _signature: Optional[dict] = None

    def __init__(self, direction: str = "rx", **values):
        protocol = self._channel.protocol
        address = {name: values.pop(name) for name in protocol.pci_type.names() if name in values}
        self.pci = protocol.make_pci(**address)       # PCI: mandatory address of this protocol
        self.direction = direction
        self.timestamp: Optional[float] = None
        super().__init__(**values)
        for name, value in (self._signature or {}).items():
            setattr(self, name, value)
        protocol.check_sdu(bytes(self))
        if direction == "rx":
            self._channel.register(self)

    # ---------------------------------------------------------------- identification

    def signature(self) -> Optional[tuple]:
        return tuple(sorted(self._signature.items())) if self._signature else None

    def matches(self, sdu: bytes) -> bool:
        if len(sdu) != ctypes.sizeof(self):
            return False
        probe = type(self).from_buffer_copy(sdu)
        return all(getattr(probe, name) == value for name, value in self._signature.items())

    # ---------------------------------------------------------------- SDU <-> PDU

    def to_pdu(self) -> Pdu:
        return Pdu(self.pci, bytes(self))

    def decode(self, pdu: Pdu) -> bool:
        if len(pdu.sdu) != ctypes.sizeof(self):
            return False
        memoryview(self).cast("B")[:] = pdu.sdu        # one copy: a reader sees the old or the new packet
        self.timestamp = pdu.timestamp
        return True

    def values(self) -> dict:
        return {name: getattr(self, name) for name, *_ in self._fields_}


class LeMessage(Message, ctypes.LittleEndianStructure):
    pass


class BeMessage(Message, ctypes.BigEndianStructure):
    pass
