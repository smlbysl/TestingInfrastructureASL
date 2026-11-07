"""Event types published on the event bus.

Events are small, immutable records. Events about a message carry copies:
- raw:   the packet as it was on the wire (logged as is)
- image: the ctypes layout of the message right after decode / pack
The RX poller may overwrite the message object while a subscriber is still working,
so subscribers read consistent values with event.snapshot().
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from generic.basemessage import BaseMessageStructure
from generic.channel import Channel
from generic.enumerations import ProtocolType


@dataclass(frozen=True)
class MessageEvent:
    message: BaseMessageStructure
    raw: bytes                          # the packet on the wire
    host_time: float                    # wall clock of this host (time.time)
    image: bytes = b""                  # ctypes layout of the message (empty for an invalid packet)

    @property
    def channel(self) -> Channel:
        return self.message._channel

    def snapshot(self) -> BaseMessageStructure:
        """A separate object of the same class holding the values of this packet.

        It is not registered and does not change when the next packet arrives.
        """
        return type(self.message).from_buffer_copy(self.image)


@dataclass(frozen=True)
class MessageReceived(MessageEvent):
    timestamp: Optional[float] = None   # arrival time from UTS (seconds)


@dataclass(frozen=True)
class MessageSent(MessageEvent):
    pass


@dataclass(frozen=True)
class InvalidReceived(MessageEvent):
    """The packet matched a message but failed validation (size, length, checksum)."""
    timestamp: Optional[float] = None


@dataclass(frozen=True)
class UnknownReceived:
    """The packet matched no registered message (channel is None if no envelope accepted it)."""
    channel: Optional[Channel]
    raw: bytes
    host_time: float
    timestamp: Optional[float] = None


@dataclass(frozen=True)
class RxTimeout:
    """A periodic RX message has not arrived within period * tolerance."""
    message: BaseMessageStructure
    age: float                          # seconds since the last packet (or since polling started)
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
# Every packet as it is on the line (envelope included). A received packet gives WireReceived
# first, then one of MessageReceived / InvalidReceived / UnknownReceived; a sent message gives
# WireSent, then MessageSent.

@dataclass(frozen=True)
class WireReceived:
    """A packet as it came from the line, before it is matched to a message."""
    channel: Optional[Channel]          # None: no envelope on the address accepted it
    protocol: ProtocolType
    interface: int
    wire: bytes
    timestamp: Optional[float]          # UTS arrival time in seconds
    host_time: float


@dataclass(frozen=True)
class WireSent:
    """A packet as it went to the line."""
    channel: Channel
    message: BaseMessageStructure
    wire: bytes
    host_time: float
