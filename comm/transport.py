"""Transport: moves bytes between channels and UTS.

TX: channel envelope -> UTS transfer on the channel's address.
RX: UTS fetch on an address -> the address's splitter -> the first channel of the address whose
    envelope accepts the packet -> RxFrame for the dispatcher.
Knows channels and bytes only; nothing about messages, signatures or timing.
"""
import time
from dataclasses import dataclass
from typing import Optional

from comm.uts import UtsClient
from generic.channel import Address, Channel
from generic.enumerations import ProtocolType
from generic.framing import Splitter

_NO_SPLIT = Splitter()


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
    def __init__(self, uts: UtsClient):
        self.uts = uts

    def send(self, channel: Channel, data: bytes) -> bytes:
        """Sends message bytes on a channel; returns the bytes put on the line."""
        wire = channel.framing.envelope.on_send(data)
        self.uts.transfer(channel.protocol, channel.interface, wire)
        return wire

    def poll(self, address: Address, channels: list[Channel]) -> list[RxFrame]:
        """Fetches an address; channels are the candidates on it, in the order they are tried."""
        protocol, interface = address
        splitter = next((ch.framing.splitter for ch in channels if ch.has_splitter), _NO_SPLIT)
        now = time.time()
        frames = []
        for item in self.uts.fetch(protocol, interface):
            for wire in splitter.split(item.data):
                channel, data = self._identify(channels, wire)
                frames.append(RxFrame(channel, data, wire, protocol, interface, item.timestamp, now))
        return frames

    @staticmethod
    def _identify(channels: list[Channel], wire: bytes) -> tuple[Optional[Channel], bytes]:
        for channel in channels:
            data = channel.framing.envelope.on_receive(wire)
            if data is not None:
                return channel, data
        return None, wire
