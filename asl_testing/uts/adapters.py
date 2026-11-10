"""Gateway adapters: PDU <-> UTS JSON, one per protocol type.

The protocol knows the bus; the adapter knows how the gateway (UTS) writes that bus in JSON.
If the gateway changes, only the adapters change.

    to_uts(protocol, pdu) -> body          TX: the POST body
    from_uts(protocol, item) -> units      RX: what protocol.receive() takes (bytes for a byte stream,
                                           a PDU for a bus whose PCI travels next to the data)
A malformed item raises UtsFormatError: a gateway problem, reported as LinkError, not a target problem.

Formats (to be checked against the real UTS):
- byte streams : {"message": [b0, b1, ...], "timestamp": t}
- timestamp    : unit unknown; time_unit is the number of seconds per UTS unit (default 1.0)
"""
from typing import Optional

from asl_testing.protocol.base import Protocol
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


# Default adapter per protocol type (the most specific class wins); extended by other protocol modules.
ADAPTERS: dict[type, type[UtsAdapter]] = {ByteStream: ByteListAdapter}


def register_adapter(protocol_type: type, adapter_type: type[UtsAdapter]) -> None:
    ADAPTERS[protocol_type] = adapter_type


def default_adapter(protocol: Protocol, time_unit: float = 1.0) -> UtsAdapter:
    for klass in type(protocol).__mro__:
        if klass in ADAPTERS:
            return ADAPTERS[klass](time_unit)
    raise TypeError(f"no UTS adapter for {type(protocol).__name__}")
