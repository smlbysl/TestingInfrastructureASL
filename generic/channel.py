"""Channel: the logical channel a message travels on.

A channel is an interface number of a protocol plus its framing. Several channels may share one
address (protocol + interface), e.g. one with an Ethernet header and one without; on RX the
envelope tells them apart. Equality is identity: every channel is defined once, in the project.

    class MyChannels(ChannelSet):
        CONTROL = Rs422Channel(0)
        DIAG    = EthernetChannel(1, Framing(envelope=EthHeader()))
        RAW     = EthernetChannel(1)

The channel is given to messages as a class default (_channel); physical settings
(IP, port, baud rate ...) are not part of it.
"""
from dataclasses import dataclass, field
from typing import ClassVar, Iterable, Iterator

from generic.enumerations import ProtocolType
from generic.framing import Envelope, Framing, Splitter

Address = tuple[ProtocolType, int]


@dataclass(eq=False)
class Channel:
    interface: int
    framing: Framing = field(default_factory=Framing)
    name: str = ""                              # set by ChannelSet

    protocol: ClassVar[ProtocolType]

    @property
    def address(self) -> Address:
        return (self.protocol, self.interface)

    @property
    def has_envelope(self) -> bool:
        return type(self.framing.envelope) is not Envelope

    @property
    def has_splitter(self) -> bool:
        return type(self.framing.splitter) is not Splitter

    def __str__(self) -> str:
        return self.name or f"{self.protocol.name}:{self.interface}"


@dataclass(eq=False)
class EthernetChannel(Channel):
    protocol = ProtocolType.ETHERNET


@dataclass(eq=False)
class Rs422Channel(Channel):
    protocol = ProtocolType.RS422


class ChannelSet:
    """The channels of a project: names them and checks the rules when the class is defined."""

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
    """On one address: at most one splitter and at most one channel without an envelope."""
    plain: dict[Address, Channel] = {}
    split: dict[Address, Channel] = {}
    for ch in channels:
        if not ch.has_envelope:
            if ch.address in plain:
                raise ValueError(f"{plain[ch.address]} and {ch} share {ch.protocol.name}:{ch.interface} "
                                 f"without an envelope; their packets could not be told apart")
            plain[ch.address] = ch
        if ch.has_splitter:
            if ch.address in split:
                raise ValueError(f"{split[ch.address]} and {ch} both define a splitter for "
                                 f"{ch.protocol.name}:{ch.interface}; an address has one splitter")
            split[ch.address] = ch


def by_address(channels: Iterable[Channel]) -> dict[Address, list[Channel]]:
    """Groups channels by address, in the order they are tried on RX: with an envelope first, plain last."""
    groups: dict[Address, list[Channel]] = {}
    for ch in channels:
        groups.setdefault(ch.address, []).append(ch)
    return {address: sorted(chans, key=lambda ch: not ch.has_envelope) for address, chans in groups.items()}
