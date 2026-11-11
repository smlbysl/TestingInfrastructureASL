"""Transport: moves bytes between a channel and its UTS interface.

TX: envelope -> channel.protocol.encode -> uts.post
RX: uts.get -> channel.protocol.decode -> splitter -> envelope -> RxFrame
Knows channels and bytes only, not messages, signatures or timing.
"""

__author__ = "İsmail Baysal"

import time
from dataclasses import dataclass
from typing import Optional

from asl_testing.channel.channel import Channel
from asl_testing.uts.client import UtsClient


@dataclass(frozen=True)
class RxFrame:
    channel: Channel
    data: bytes                         # message bytes (envelope removed); the wire if rejected
    wire: bytes                         # bytes on the line
    timestamp: Optional[float]          # UTS time in seconds
    host_time: float                    # host time (time.time) of the poll
    accepted: bool = True               # False: the channel's envelope rejected the packet


class Transport:
    def __init__(self, uts: UtsClient):
        self.uts = uts

    def send(self, channel: Channel, data: bytes) -> bytes:
        """Sends message bytes on a channel; returns the bytes on the line."""
        wire = channel.framing.envelope.on_send(data)
        self.uts.post(channel.protocol.path, channel.interface, channel.protocol.encode(wire))
        return wire

    def poll(self, channel: Channel) -> list[RxFrame]:
        """Reads what UTS received on the channel's interface since the last call."""
        now = time.time()
        frames = []
        for item in self.uts.get(channel.protocol.path, channel.interface):
            received = channel.protocol.decode(item)
            for wire in channel.framing.splitter.split(received.data):
                data = channel.framing.envelope.on_receive(wire)
                accepted = data is not None
                frames.append(RxFrame(channel, data if accepted else wire, wire, received.timestamp, now, accepted))
        return frames
