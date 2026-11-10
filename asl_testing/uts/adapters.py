"""Gateway adapters: PDU <-> UTS JSON, one per protocol type.

The protocol knows the bus; the adapter knows how the gateway (UTS) writes that bus in JSON.
If the gateway changes, only the adapters change.

    to_uts(protocol, pdu) -> body          TX: the POST body
    from_uts(protocol, item) -> units      RX: what protocol.receive() takes (bytes for a byte stream,
                                           a PDU for a bus whose PCI travels next to the data)
A malformed item raises UtsFormatError: a gateway problem, reported as LinkError, not a target problem.

Formats (to be checked against the real UTS):
- byte streams : {"message": [b0, b1, ...], "timestamp": t}
- 1553         : {"message": [node, subnet, word_count, w0, w1, ...], "timestamp": t}
- CAN          : {"id": can_id, "message": [b0, ...], "timestamp": t}        (assumption)
- timestamp    : unit unknown; time_unit is the number of seconds per UTS unit (default 1.0)
"""
from typing import Optional

from asl_testing.protocol.base import Protocol
from asl_testing.protocol.can import Can, CanPci
from asl_testing.protocol.mil1553 import Mil1553, Mil1553Pci
from asl_testing.protocol.pdu import Pdu
from asl_testing.protocol.stream import ByteStream
from asl_testing.uts.client import UtsError


class UtsFormatError(UtsError):
    """An item from UTS is not in the expected format."""


class UtsAdapter:
    def __init__(self, time_unit: float = 1.0):
        self.time_unit = time_unit

    def to_uts(self, protocol: Protocol, pdu: Pdu) -> dict:
        raise NotImplementedError

    def from_uts(self, protocol: Protocol, item: dict) -> list:
        raise NotImplementedError

    def timestamp(self, item: dict) -> Optional[float]:
        """Seconds; None if the item has no time."""
        value = item.get("timestamp")
        return None if value is None else value * self.time_unit

    def to_uts_time(self, seconds: float):
        """Seconds -> UTS units (used by the fake UTS to stamp items like the real one)."""
        return seconds / self.time_unit

    @staticmethod
    def _field(item: dict, name: str):
        try:
            return item[name]
        except (KeyError, TypeError) as error:
            raise UtsFormatError(f"item has no '{name}': {item!r}") from error

    @staticmethod
    def _bytes(values) -> bytes:
        try:
            return bytes(values)
        except (TypeError, ValueError) as error:
            raise UtsFormatError(f"not a byte list: {values!r}") from error


class ByteListAdapter(UtsAdapter):
    """Byte streams: the line bytes (header included) as a list of ints."""

    def to_uts(self, protocol: ByteStream, pdu: Pdu) -> dict:
        return {"message": list(protocol.wire(pdu))}

    def from_uts(self, protocol: ByteStream, item: dict) -> list:
        return [self._bytes(self._field(item, "message"))]


class Mil1553Adapter(UtsAdapter):
    """1553: [node, subnet, word count, words ...] in one list."""

    def to_uts(self, protocol: Mil1553, pdu: Pdu) -> dict:
        words = protocol.to_words(pdu.sdu)
        return {"message": [pdu.pci.node, pdu.pci.subnet, len(words), *words]}

    def from_uts(self, protocol: Mil1553, item: dict) -> list:
        values = self._field(item, "message")
        if not isinstance(values, list) or len(values) < 3:
            raise UtsFormatError(f"1553: {values!r} has no node / subnet / word count")
        node, subnet, count, *words = values
        if count != len(words):
            raise UtsFormatError(f"1553: word count {count}, but {len(words)} words")
        if not all(isinstance(w, int) and 0 <= w <= 0xFFFF for w in words):
            raise UtsFormatError(f"1553: {words!r} are not 16-bit words")
        return [Pdu(Mil1553Pci(node, subnet), protocol.from_words(words), self.timestamp(item))]


class CanAdapter(UtsAdapter):
    """CAN: the id next to the data bytes (assumed layout)."""

    def to_uts(self, protocol: Can, pdu: Pdu) -> dict:
        return {"id": pdu.pci.can_id, "message": list(pdu.sdu)}

    def from_uts(self, protocol: Can, item: dict) -> list:
        can_id = self._field(item, "id")
        data = self._bytes(self._field(item, "message"))
        return [Pdu(CanPci(can_id), data, self.timestamp(item))]


# Default adapter per protocol type (the most specific class wins); register_adapter adds new ones.
ADAPTERS: dict[type, type[UtsAdapter]] = {ByteStream: ByteListAdapter, Mil1553: Mil1553Adapter, Can: CanAdapter}


def register_adapter(protocol_type: type, adapter_type: type[UtsAdapter]) -> None:
    ADAPTERS[protocol_type] = adapter_type


def default_adapter(protocol: Protocol, time_unit: float = 1.0) -> UtsAdapter:
    for klass in type(protocol).__mro__:
        if klass in ADAPTERS:
            return ADAPTERS[klass](time_unit)
    raise TypeError(f"no UTS adapter for {type(protocol).__name__}")
