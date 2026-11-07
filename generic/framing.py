"""Framing: what happens to bytes between a message and the line.

- Splitter (stream level): turns what UTS returned for an address into packets.
  It works before the packet is matched to a channel, so one address has at most one splitter.
- Envelope (packet level): what is added around a message on a channel.

The defaults do nothing, so a channel without framing passes bytes through unchanged.
"""
from dataclasses import dataclass, field
from typing import Optional


class Splitter:
    def split(self, data: bytes) -> list[bytes]:
        """Returns the packets contained in data. Default: data is one packet."""
        return [data]

    def reset(self) -> None:
        """Drops any partial packet kept between two reads."""


class Envelope:
    def on_send(self, data: bytes) -> bytes:
        """TX: message bytes -> bytes on the line."""
        return data

    def on_receive(self, wire: bytes) -> Optional[bytes]:
        """RX: bytes on the line -> message bytes.

        Returns None when the packet does not belong to this channel, so the next channel
        on the same address is tried.
        """
        return wire


@dataclass
class Framing:
    splitter: Splitter = field(default_factory=Splitter)
    envelope: Envelope = field(default_factory=Envelope)
