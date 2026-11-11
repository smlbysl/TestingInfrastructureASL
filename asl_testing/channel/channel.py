"""Channel: one UTS interface, its protocol object and its framing.

    class MyChannels(ChannelSet):
        CONTROL = Rs422Channel(0)
        DIAG    = EthernetChannel(1, Framing(envelope=EthHeader()))
        BUS_A   = Mil1553Channel(1, protocol=Mil1553Protocol(byte_order="big"))

Messages get their channel as a class default (_channel). Equality is identity: each channel is
defined once in the project, and an interface has one channel. Physical settings (IP, port, baud rate)
are not part of a channel.
"""

__author__ = "İsmail Baysal"

from dataclasses import dataclass, field
from typing import ClassVar, Iterable, Iterator, Optional

from asl_testing.channel.framing import Framing
from asl_testing.protocol.base import Protocol
from asl_testing.protocol.ethernet import EthernetProtocol
from asl_testing.protocol.mil1553 import Mil1553Protocol
from asl_testing.protocol.rs422 import Rs422Protocol


@dataclass(eq=False)
class Channel:
    interface: int
    framing: Framing = field(default_factory=Framing)
    protocol: Optional[Protocol] = None         # None: an instance of default_protocol
    name: str = ""                              # set by ChannelSet

    default_protocol: ClassVar[type[Protocol]]

    def __post_init__(self):
        if self.protocol is None:
            self.protocol = self.default_protocol()

    @property
    def key(self) -> tuple[str, int]:
        """The UTS interface: (protocol path, interface number)."""
        return (self.protocol.path, self.interface)

    def __str__(self) -> str:
        return self.name or f"{self.protocol.path}:{self.interface}"


@dataclass(eq=False)
class EthernetChannel(Channel):
    default_protocol = EthernetProtocol


@dataclass(eq=False)
class Rs422Channel(Channel):
    default_protocol = Rs422Protocol


@dataclass(eq=False)
class Mil1553Channel(Channel):
    default_protocol = Mil1553Protocol


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
    """One channel per UTS interface."""
    seen: dict[tuple[str, int], Channel] = {}
    for ch in channels:
        if ch.key in seen:
            raise ValueError(f"{seen[ch.key]} and {ch} use the same interface {ch.protocol.path}:{ch.interface}; "
                             f"an interface has one channel")
        seen[ch.key] = ch
