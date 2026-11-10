"""Transport: moves PDUs between channels and UTS, through the gateway adapters.

TX: (PCI, SDU) -> protocol rules -> adapter -> UTS POST on the channel's address.
RX: UTS GET on an address -> adapter -> units -> the address's splitter (byte streams) ->
    the first channel of the address whose protocol accepts the unit -> RxFrame for the dispatcher.
Knows channels, protocols and adapters; nothing about messages, signatures or timing.
"""
import time
from dataclasses import dataclass
from typing import Optional

from asl_testing.channel.channel import Address, Channel
from asl_testing.protocol.base import Protocol
from asl_testing.protocol.pdu import Pci, Pdu
from asl_testing.uts.adapters import UtsAdapter, UtsFormatError, default_adapter
from asl_testing.uts.client import UtsClient


@dataclass(frozen=True)
class RxFrame:
    channel: Optional[Channel]          # None: no channel on the address accepted the unit
    pdu: Optional[Pdu]                  # None when no channel accepted it
    wire: bytes                         # the packet as it was on the line (SDU for buses with PCI next to it)
    protocol: str                       # UTS path
    interface: int
    timestamp: Optional[float]          # UTS arrival time in seconds
    host_time: float                    # wall clock of this host when polled
    error: Optional[Exception] = None   # the UTS item was malformed (UtsFormatError); nothing else is set

    @property
    def data(self) -> bytes:
        """The SDU (message bytes), or the line bytes if no channel accepted the packet."""
        return self.pdu.sdu if self.pdu is not None else self.wire


class Transport:
    def __init__(self, uts: UtsClient, adapters: Optional[dict[type, UtsAdapter]] = None, time_unit: float = 1.0):
        self.uts = uts
        self.time_unit = time_unit
        self._overrides = dict(adapters or {})          # protocol type -> adapter instance
        self._adapters: dict[type, UtsAdapter] = {}

    def adapter(self, protocol: Protocol) -> UtsAdapter:
        kind = type(protocol)
        if kind not in self._adapters:
            override = next((self._overrides[k] for k in kind.__mro__ if k in self._overrides), None)
            self._adapters[kind] = override or default_adapter(protocol, self.time_unit)
        return self._adapters[kind]

    def send(self, channel: Channel, pci: Pci, sdu: bytes) -> bytes:
        """Sends an SDU with its PCI on a channel; returns the packet as it went to the line."""
        protocol = channel.protocol
        protocol.check_sdu(sdu)
        pdu = Pdu(pci, sdu)
        self.uts.post(protocol.path, channel.interface, self.adapter(protocol).to_uts(protocol, pdu))
        return protocol.wire(pdu)

    def poll(self, address: Address, channels: list[Channel]) -> list[RxFrame]:
        """Fetches an address; channels are the candidates on it, in the order they are tried.

        A malformed item gives a frame with `error` set; the other items of the answer are still delivered.
        """
        path, interface = address
        protocol = channels[0].protocol                  # one protocol type per address (check_channels)
        adapter = self.adapter(protocol)
        splitter = next((ch.splitter for ch in channels if ch.splitter is not None), None)
        now = time.time()
        frames: list[RxFrame] = []
        for item in self.uts.get(path, interface):
            try:
                timestamp = adapter.timestamp(item)
                units = adapter.from_uts(protocol, item)
            except UtsFormatError as error:
                frames.append(RxFrame(None, None, b"", path, interface, None, now, error))
                continue
            for unit in units:
                parts = splitter.split(unit) if splitter is not None and isinstance(unit, bytes) else [unit]
                for part in parts:
                    channel, pdu = self._identify(channels, part, timestamp)
                    wire = channel.protocol.wire(pdu) if pdu is not None else _as_bytes(part)
                    frames.append(RxFrame(channel, pdu, wire, path, interface, timestamp, now))
        return frames

    @staticmethod
    def _identify(channels: list[Channel], unit, timestamp: Optional[float]) -> tuple[Optional[Channel], Optional[Pdu]]:
        for channel in channels:
            pdu = channel.protocol.receive(unit, timestamp)
            if pdu is not None:
                return channel, pdu
        return None, None


def _as_bytes(unit) -> bytes:
    return unit if isinstance(unit, bytes) else getattr(unit, "sdu", b"")
