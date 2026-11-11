"""Transport: moves bytes between channels and UTS.

TX: envelope -> protocol.encode -> uts.post
RX: uts.get -> protocol.decode -> splitter -> envelope of each channel on the address -> RxFrame
Knows channels and bytes only, not messages, signatures or timing. A channel type without a
protocol object (CAN) uses uts.transfer / uts.fetch.
"""

__author__ = "İsmail Baysal"

import time
from dataclasses import dataclass
from typing import Optional

from asl_testing.uts.client import UtsClient
from asl_testing.channel.channel import Address, Channel
from asl_testing.channel.channel import ProtocolType
from asl_testing.channel.framing import Splitter
from asl_testing.protocol.base import Protocol, Received
from asl_testing.protocol.defaults import default_protocols

_NO_SPLIT = Splitter()


@dataclass(frozen=True)
class RxFrame:
    channel: Optional[Channel]          # None: no envelope on the address accepted the packet
    data: bytes                         # message bytes (envelope removed)
    wire: bytes                         # bytes on the line
    protocol: ProtocolType
    interface: int
    timestamp: Optional[float]          # UTS time in seconds
    host_time: float                    # host time (time.time) of the poll


class Transport:
    def __init__(self, uts: UtsClient, protocols: Optional[dict[ProtocolType, Protocol]] = None):
        self.uts = uts
        self.protocols = default_protocols() if protocols is None else dict(protocols)

    def send(self, channel: Channel, data: bytes) -> bytes:
        """Sends message bytes on a channel; returns the bytes on the line."""
        wire = channel.framing.envelope.on_send(data)
        protocol = self.protocols.get(channel.protocol)
        if protocol is None:
            self.uts.transfer(channel.protocol, channel.interface, wire)
        else:
            self.uts.post(protocol.path, channel.interface, protocol.encode(wire))
        return wire

    def poll(self, address: Address, channels: list[Channel]) -> list[RxFrame]:
        """Reads an address; channels are its channels in the order their envelopes are tried."""
        kind, interface = address
        splitter = next((ch.framing.splitter for ch in channels if ch.has_splitter), _NO_SPLIT)
        now = time.time()
        frames = []
        for received in self._receive(kind, interface):
            for wire in splitter.split(received.data):
                channel, data = self._identify(channels, wire)
                frames.append(RxFrame(channel, data, wire, kind, interface, received.timestamp, now))
        return frames

    def _receive(self, kind: ProtocolType, interface: int) -> list[Received]:
        protocol = self.protocols.get(kind)
        if protocol is None:
            return [Received(item.data, item.timestamp) for item in self.uts.fetch(kind, interface)]
        return [protocol.decode(item) for item in self.uts.get(protocol.path, interface)]

    @staticmethod
    def _identify(channels: list[Channel], wire: bytes) -> tuple[Optional[Channel], bytes]:
        for channel in channels:
            data = channel.framing.envelope.on_receive(wire)
            if data is not None:
                return channel, data
        return None, wire
