"""Transport: moves bytes on a channel through the UTS client.

Knows channels and bytes only; nothing about messages, signatures or timing.
Line-specific framing (if ever needed) belongs here.
"""
import time
from dataclasses import dataclass
from typing import Optional

from comm.uts import UtsClient
from generic.channel import Channel


@dataclass(frozen=True)
class RxFrame:
    channel: Channel
    data: bytes
    timestamp: Optional[float]          # UTS arrival time in seconds
    host_time: float                    # wall clock of this host when polled


class Transport:
    def __init__(self, uts: UtsClient):
        self.uts = uts

    def send(self, channel: Channel, data: bytes) -> None:
        self.uts.transfer(channel.protocol, channel.interface, data)

    def poll(self, channel: Channel) -> list[RxFrame]:
        now = time.time()
        return [RxFrame(channel, f.data, f.timestamp, now)
                for f in self.uts.fetch(channel.protocol, channel.interface)]
