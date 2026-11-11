"""Framing: what happens to the bytes between a message and the line.

Splitter   stream level: cuts what UTS returned for an address into packets (one per address)
Envelope   packet level: what a channel adds around a message (e.g. a header)

The defaults pass the bytes through unchanged.
"""

__author__ = "İsmail Baysal"

from dataclasses import dataclass, field
from typing import Optional


class Splitter:
    def split(self, data: bytes) -> list[bytes]:
        """Packets in data. Default: data is one packet."""
        return [data]


class Envelope:
    offset = 0      # header size in front of the message; used for UTS filters

    def on_send(self, data: bytes) -> bytes:
        """TX: message bytes -> bytes on the line."""
        return data

    def on_receive(self, wire: bytes) -> Optional[bytes]:
        """RX: bytes on the line -> message bytes, or None if the packet is not for this channel."""
        return wire


@dataclass
class Framing:
    splitter: Splitter = field(default_factory=Splitter)
    envelope: Envelope = field(default_factory=Envelope)
