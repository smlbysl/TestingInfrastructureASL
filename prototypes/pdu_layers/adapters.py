"""Gateway adapters: PDU <-> UTS JSON, one per protocol.

The protocol knows the bus, the adapter knows how the gateway (UTS) writes that bus in JSON.
If the gateway changes, only the adapters change.

Assumed UTS formats (to be checked against the real UTS):
- byte streams : {"message": [b0, b1, ...], "timestamp": t}
- 1553         : {"message": [node, subnet, word_count, w0, w1, ...], "timestamp": t}
- CAN          : {"id": can_id, "message": [b0, ...], "timestamp": t}       (assumption)
- timestamp unit: unknown, set by time_unit (seconds per UTS unit)
"""
from typing import Optional

from .pdu import CanPci, Mil1553Pci, Pdu
from .protocols import ByteStream, Can, Mil1553, Protocol


class UtsFormatError(Exception):
    """The gateway answered in an unexpected format: a gateway problem, not a target problem."""


class UtsAdapter:
    def __init__(self, time_unit: float = 1e-6):
        self.time_unit = time_unit

    def to_uts(self, protocol: Protocol, pdu: Pdu) -> dict:
        raise NotImplementedError

    def from_uts(self, protocol: Protocol, item: dict) -> Optional[Pdu]:
        """The PDU; None if it does not belong to this channel; UtsFormatError if the item is malformed."""
        raise NotImplementedError

    def _time(self, item: dict) -> Optional[float]:
        t = item.get("timestamp")
        return None if t is None else t * self.time_unit

    @staticmethod
    def _bytes(values) -> bytes:
        try:
            return bytes(values)
        except (TypeError, ValueError) as error:
            raise UtsFormatError(f"not a byte list: {values!r}") from error


class ByteListAdapter(UtsAdapter):
    def to_uts(self, protocol: ByteStream, pdu: Pdu) -> dict:
        return {"message": list(protocol.to_bytes(pdu))}

    def from_uts(self, protocol: ByteStream, item: dict) -> Optional[Pdu]:
        return protocol.from_bytes(self._bytes(item["message"]), self._time(item))


class Mil1553Adapter(UtsAdapter):
    def to_uts(self, protocol: Mil1553, pdu: Pdu) -> dict:
        words = protocol.to_words(pdu.sdu)
        return {"message": [pdu.pci.node, pdu.pci.subnet, len(words), *words]}

    def from_uts(self, protocol: Mil1553, item: dict) -> Optional[Pdu]:
        values = item["message"]
        if len(values) < 3:
            raise UtsFormatError(f"1553: {values!r} has no node / subnet / word count")
        node, subnet, count, *words = values
        if count != len(words):
            raise UtsFormatError(f"1553: word count {count}, but {len(words)} words")
        if any(not 0 <= w <= 0xFFFF for w in words):
            raise UtsFormatError(f"1553: {words!r} are not 16-bit words")
        return Pdu(Mil1553Pci(node, subnet), protocol.from_words(words), self._time(item))


class CanAdapter(UtsAdapter):
    def to_uts(self, protocol: Can, pdu: Pdu) -> dict:
        return {"id": pdu.pci.can_id, "message": list(pdu.sdu)}

    def from_uts(self, protocol: Can, item: dict) -> Optional[Pdu]:
        return Pdu(CanPci(item["id"]), self._bytes(item["message"]), self._time(item))


def adapter_for(protocol: Protocol) -> UtsAdapter:
    """Default adapter of a protocol for the UTS gateway."""
    if isinstance(protocol, ByteStream):
        return ByteListAdapter()
    if isinstance(protocol, Mil1553):
        return Mil1553Adapter()
    if isinstance(protocol, Can):
        return CanAdapter()
    raise TypeError(f"no UTS adapter for {type(protocol).__name__}")
