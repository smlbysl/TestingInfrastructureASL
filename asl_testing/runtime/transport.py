"""Transport: moves bytes between channels and UTS.

TX: channel envelope -> protocol.encode -> UTS post on the channel's address.
RX: UTS get on an address -> protocol.decode -> the address's splitter -> the first channel of the
    address whose envelope accepts the packet -> RxFrame for the dispatcher.
Knows channels and bytes only; nothing about messages, signatures or timing.

Protocols are looked up by the channel's protocol type. A type without a protocol object yet (RS422,
CAN) still uses the old byte path (uts.transfer / uts.fetch); they move over one by one.
"""
import logging
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
_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RxFrame:
    channel: Optional[Channel]          # None: no envelope on the address accepted the packet
    data: bytes                         # message bytes (inside the envelope)
    wire: bytes                         # packet as it was on the line
    protocol: ProtocolType
    interface: int
    timestamp: Optional[float]          # UTS arrival time in seconds
    host_time: float                    # wall clock of this host when polled


class Transport:
    def __init__(self, uts: UtsClient, protocols: Optional[dict[ProtocolType, Protocol]] = None):
        self.uts = uts
        self.protocols = default_protocols() if protocols is None else dict(protocols)

    def send(self, channel: Channel, data: bytes) -> bytes:
        """Sends message bytes on a channel; returns the bytes put on the line."""
        wire = channel.framing.envelope.on_send(data)
        protocol = self.protocols.get(channel.protocol)
        if protocol is None:                                    # not moved to a protocol object yet
            self.uts.transfer(channel.protocol, channel.interface, wire)
        else:
            self.uts.post(protocol.path, channel.interface, protocol.encode(wire))
        return wire

    def poll(self, address: Address, channels: list[Channel]) -> list[RxFrame]:
        """Fetches an address; channels are the candidates on it, in the order they are tried."""
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
        if protocol is None:                                    # not moved to a protocol object yet
            return [Received(item.data, item.timestamp) for item in self.uts.fetch(kind, interface)]
        received = []
        for item in self.uts.get(protocol.path, interface):
            try:
                received.append(protocol.decode(item))
            except Exception:                   # one malformed item must not drop the others
                _log.exception("%s:%d: UTS item not in %s format, skipped: %r",
                               kind.name, interface, type(protocol).__name__, item)
        return received

    @staticmethod
    def _identify(channels: list[Channel], wire: bytes) -> tuple[Optional[Channel], bytes]:
        for channel in channels:
            data = channel.framing.envelope.on_receive(wire)
            if data is not None:
                return channel, data
        return None, wire
