"""Channel: one interface of a bus and its framing.

    class MyChannels(ChannelSet):
        CONTROL = Rs422Channel(0)
        DIAG    = EthernetChannel(1, Framing(envelope=EthHeader()))
        BUS_A   = Mil1553Channel(1, byte_order="big")

A channel names the bus and the interface; how its bytes are carried is the backend's business.

Messages get their channel as a class default (_channel). Equality is identity: each channel is
defined once in the project, and an interface has one channel. Physical settings (IP, port, baud rate)
are not part of a channel.
"""

__author__ = "İsmail Baysal"

from dataclasses import dataclass, field
from typing import ClassVar, Iterable, Iterator

from asl_testing.channel.framing import Framing


@dataclass(eq=False)
class Channel:
    interface: int
    framing: Framing = field(default_factory=Framing)
    name: str = ""                              # set by ChannelSet

    bus: ClassVar[str]                          # bus type; the backend chooses its format by it

    @property
    def key(self) -> tuple[str, int]:
        """The interface: (bus, interface number)."""
        return (self.bus, self.interface)

    def __str__(self) -> str:
        return self.name or f"{self.bus}:{self.interface}"


@dataclass(eq=False)
class EthernetChannel(Channel):
    bus = "ethernet"


@dataclass(eq=False)
class Rs422Channel(Channel):
    bus = "serial"


@dataclass(eq=False)
class Mil1553Channel(Channel):
    bus = "mil1553"

    byte_order: str = "little"                  # of the 16-bit words; must match the message structures


class ChannelSet:
    """Channels of a project: names them and checks that no interface is used twice."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name, value in vars(cls).items():
            if isinstance(value, Channel):
                value.name = name
        check_channels(cls.all())

    @classmethod
    def all(cls) -> Iterator[Channel]:
        for klass in reversed(cls.__mro__):
            for value in vars(klass).values():
                if isinstance(value, Channel):
                    yield value


def check_channels(channels: Iterable[Channel]) -> None:
    """One channel per interface."""
    seen: dict[tuple[str, int], Channel] = {}
    for ch in channels:
        if ch.key in seen:
            raise ValueError(f"{seen[ch.key]} and {ch} use the same interface {ch.bus}:{ch.interface}; "
                             f"an interface has one channel")
        seen[ch.key] = ch
