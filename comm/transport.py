"""Transport: moves bytes between channels and UTS links.

TX: channel rules + envelope (Channel.to_wire) -> UTS transfer on the channel's link.
RX: UTS fetch on a link -> link splitter -> the first channel of the link whose envelope accepts
    the packet -> that channel's raw rules -> RxFrame for the dispatcher.
Knows nothing about messages, signatures or timing.
"""
import time
from dataclasses import dataclass
from typing import Optional

from comm.link import Link
from comm.uts.base import UtsClient
from generic.channel import Channel, ChannelSet


@dataclass(frozen=True)
class RxFrame:
    link: Link
    channel: Optional[Channel]          # None: no envelope on the link accepted the packet
    data: bytes                         # message bytes (inside the envelope)
    wire: bytes                         # packet as it was on the line
    timestamp: Optional[float]          # UTS arrival time in seconds
    host_time: float                    # wall clock of this host when polled


@dataclass(frozen=True)
class RxPoll:
    frames: list[RxFrame]
    overflow: bool


class Transport:
    def __init__(self, uts: UtsClient, channels: type[ChannelSet]):
        self.uts = uts
        self.channels = channels

    def send(self, channel: Channel, data: bytes) -> bytes:
        """Sends message bytes on a channel; returns the bytes put on the line."""
        wire = channel.to_wire(data)
        self.uts.transfer(channel.link, wire)
        return wire

    def poll(self, link: Link) -> RxPoll:
        fetched = self.uts.fetch(link)
        now = time.time()
        candidates = self.channels.on_link(link)
        frames = []
        for item in fetched.frames:
            for wire in link.splitter.split(item.data):
                channel, data = self._identify(candidates, wire)
                if channel is not None:
                    data = channel.apply_rx_rules(data)
                    if data is None:
                        continue                    # dropped by a raw rule
                frames.append(RxFrame(link, channel, data, wire, item.timestamp, now))
        return RxPoll(frames, fetched.overflow)

    @staticmethod
    def _identify(candidates: list[Channel], wire: bytes) -> tuple[Optional[Channel], bytes]:
        for channel in candidates:
            data = channel.envelope.on_receive(wire)
            if data is not None:
                return channel, data
        return None, wire
