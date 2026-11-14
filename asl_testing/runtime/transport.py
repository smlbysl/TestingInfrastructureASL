"""Transport: moves bytes between a channel and the backend.

TX: envelope -> backend.send
RX: backend.receive -> splitter -> envelope -> RxFrame
Knows channels and bytes only, not messages, signatures or timing.
"""

__author__ = "İsmail Baysal"

import time
from dataclasses import dataclass
from typing import Optional

from asl_testing.channel.channel import Channel
from asl_testing.backend.base import Backend, BackendError, Response


@dataclass(frozen=True)
class RxFrame:
    channel: Channel
    data: bytes                         # message bytes (envelope removed); the wire if rejected
    wire: bytes                         # bytes on the line
    timestamp: Optional[float]          # backend time in seconds
    host_time: float                    # host time (time.time) of the poll
    accepted: bool = True               # False: the channel's envelope rejected the packet


class Transport:
    def __init__(self, backend: Backend):
        self.backend = backend

    def send(self, channel: Channel, data: bytes) -> tuple[bytes, Response]:
        """Sends message bytes on a channel; returns the bytes on the line and the backend's response."""
        wire = channel.framing.envelope.on_send(data)
        return wire, self.backend.send(channel, wire)

    def poll(self, channel: Channel) -> tuple[list[RxFrame], bool]:
        """Reads what the channel's interface received since the last call; BackendError if the request failed.

        Returns the frames and whether the backend's receive buffer overflowed before this call.
        """
        now = time.time()
        response = self.backend.receive(channel)
        if not response.ok:
            raise BackendError(response)
        frames = []
        for received in response.data:
            for wire in channel.framing.splitter.split(received.data):
                data = channel.framing.envelope.on_receive(wire)
                accepted = data is not None
                frames.append(RxFrame(channel, data if accepted else wire, wire, received.timestamp, now, accepted))
        return frames, response.overflow
