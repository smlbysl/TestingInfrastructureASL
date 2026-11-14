"""FakeBackend: backend stand-in for development and tests; no UTS format involved."""

__author__ = "İsmail Baysal"

import threading
import time
from collections import defaultdict
from typing import Optional

from asl_testing.backend.base import Backend, Received, Response
from asl_testing.channel.channel import Channel


class FakeBackend(Backend):
    """send() records what is sent; inject() plays the device; receive() drains the receive buffer."""

    def __init__(self):
        self.sent: list[tuple[Channel, bytes]] = []                    # (channel, bytes on the line)
        self._received: dict[tuple[str, int], list[Received]] = defaultdict(list)
        self._overflowed: set[tuple[str, int]] = set()
        self._lock = threading.Lock()         # inject (test thread) vs receive (RX thread)

    def send(self, channel: Channel, data: bytes) -> Response:
        self.sent.append((channel, bytes(data)))
        return Response(ok=True)

    def receive(self, channel: Channel) -> Response:
        with self._lock:
            overflow = channel.key in self._overflowed
            self._overflowed.discard(channel.key)
            return Response(ok=True, data=self._received.pop(channel.key, []), overflow=overflow)

    def overflow(self, channel: Channel) -> None:
        """The next receive of the channel reports that packets were lost."""
        with self._lock:
            self._overflowed.add(channel.key)

    def inject(self, channel: Channel, data: bytes, timestamp: Optional[float] = None) -> None:
        """The device sent data (bytes on the line) on the channel's interface."""
        stamp = time.time() if timestamp is None else timestamp
        with self._lock:
            self._received[channel.key].append(Received(bytes(data), stamp))
