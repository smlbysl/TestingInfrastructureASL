"""Transport: moves bytes between a channel and its UTS interface.

TX: envelope -> adapter.send
RX: adapter.receive -> splitter -> envelope -> RxFrame
Knows channels and bytes only, not messages, signatures or timing.
"""

__author__ = "İsmail Baysal"

import time
from dataclasses import dataclass
from typing import Optional

from asl_testing.channel.channel import Channel
from asl_testing.adapter.base import Adapter


@dataclass(frozen=True)
class RxFrame:
    channel: Channel
    data: bytes                         # message bytes (envelope removed); the wire if rejected
    wire: bytes                         # bytes on the line
    timestamp: Optional[float]          # UTS time in seconds
    host_time: float                    # host time (time.time) of the poll
    accepted: bool = True               # False: the channel's envelope rejected the packet


class Transport:
    def __init__(self, adapter: Adapter):
        self.adapter = adapter

    def send(self, channel: Channel, data: bytes) -> tuple[bytes, Optional[float]]:
        """Sends message bytes on a channel; returns the bytes on the line and the adapter's time of the send."""
        wire = channel.framing.envelope.on_send(data)
        return wire, self.adapter.send(channel, wire)

    def poll(self, channel: Channel) -> tuple[list[RxFrame], bool]:
        """Reads what UTS received on the channel's interface since the last call.

        Returns the frames and whether the receive buffer of the adapter lost packets before them.
        """
        now = time.time()
        frames = []
        polled = self.adapter.receive(channel)
        for received in polled.received:
            for wire in channel.framing.splitter.split(received.data):
                data = channel.framing.envelope.on_receive(wire)
                accepted = data is not None
                frames.append(RxFrame(channel, data if accepted else wire, wire, received.timestamp, now, accepted))
        return frames, polled.overflow
