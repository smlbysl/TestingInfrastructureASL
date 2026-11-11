"""Event types published on the event bus (immutable).

Message events carry copies: raw (bytes on the wire) and image (ctypes layout after decode / pack).
The object may change while a subscriber works, so subscribers read values with event.snapshot().
"""

from __future__ import annotations

__author__ = "İsmail Baysal"

from dataclasses import dataclass
from typing import Optional

from asl_testing.message.base import BaseMessageStructure
from asl_testing.channel.channel import Channel


@dataclass(frozen=True)
class MessageEvent:
    message: BaseMessageStructure
    raw: bytes                          # bytes on the wire
    host_time: float                    # host time (time.time)
    image: bytes = b""                  # ctypes layout; empty for an invalid packet

    @property
    def channel(self) -> Channel:
        return self.message._channel

    def snapshot(self) -> BaseMessageStructure:
        """Separate object with the values of this packet (not registered)."""
        return type(self.message).from_buffer_copy(self.image)


@dataclass(frozen=True)
class MessageReceived(MessageEvent):
    timestamp: Optional[float] = None   # UTS time in seconds


@dataclass(frozen=True)
class MessageSent(MessageEvent):
    pass


@dataclass(frozen=True)
class InvalidReceived(MessageEvent):
    """Matched a message but failed validation (size, length, checksum)."""
    timestamp: Optional[float] = None


@dataclass(frozen=True)
class UnknownReceived:
    """Matched no message (or the channel's envelope rejected it)."""
    channel: Channel
    raw: bytes
    host_time: float
    timestamp: Optional[float] = None


@dataclass(frozen=True)
class RxTimeout:
    """A periodic RX message did not arrive within period * tolerance."""
    message: BaseMessageStructure
    age: float                          # seconds since the last packet or since polling started
    host_time: float


@dataclass(frozen=True)
class RxRestored:
    """A message that had timed out arrived again."""
    message: BaseMessageStructure
    host_time: float


@dataclass(frozen=True)
class LinkError:
    """A UTS request failed."""
    channel: Optional[Channel]
    operation: str                      # "send" or "poll"
    error: Exception
    host_time: float


# ---------------------------------------------------------------- line level
# Bytes on the line, envelope included. RX: WireReceived, then Message/Invalid/UnknownReceived.
# TX: WireSent, then MessageSent.

@dataclass(frozen=True)
class WireReceived:
    """A packet from the line, before it is matched to a message."""
    channel: Channel
    wire: bytes
    timestamp: Optional[float]          # UTS time in seconds
    host_time: float


@dataclass(frozen=True)
class WireSent:
    """A packet sent to the line."""
    channel: Channel
    message: BaseMessageStructure
    wire: bytes
    host_time: float
