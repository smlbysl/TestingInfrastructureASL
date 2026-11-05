"""Framing: what happens to bytes between a message and the line.

- Splitter (stream level, belongs to a Link): turns what UTS returned for an interface into packets.
- Envelope (packet level, belongs to a Channel): what is added around a message on that channel.

The defaults do nothing, so a link or channel without framing passes bytes through unchanged.
"""
from typing import Optional


class Splitter:
    def split(self, data: bytes) -> list[bytes]:
        """Returns the packets contained in data. Default: data is one packet."""
        return [data]

    def reset(self) -> None:
        """Drops any partial packet kept between two reads (called when buffers are cleared)."""


class Envelope:
    def on_send(self, data: bytes) -> bytes:
        """TX: message bytes -> bytes on the line."""
        return data

    def on_receive(self, wire: bytes) -> Optional[bytes]:
        """RX: bytes on the line -> message bytes.

        Returns None when the packet does not belong to this envelope, so the next channel
        on the same link is tried.
        """
        return wire
