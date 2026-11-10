"""Channel: one line a message travels on = an interface + a protocol object + its registry.

The protocol knows the bus (PCI, header, splitter); the channel adds the interface number and the
messages registered on it. Several channels may share one address (UTS path + interface), e.g. one
with an Ethernet header and one without; on RX the protocol (its header) tells them apart.
Equality is identity: every channel is defined once, in the project.

    class MyChannels(ChannelSet):
        CONTROL = Rs422Channel(0)
        DIAG    = EthernetChannel(1, header=EthHeader())
        RAW     = EthernetChannel(1)
        BUS_A   = Mil1553Channel(1)
        CAN0    = CanChannel(0)

Messages get the channel as a class default (_channel). Physical settings (IP, port, baud rate ...)
are not part of it.
"""
from typing import Iterable, Iterator, Optional

from asl_testing.channel.registry import ChannelRegistry
from asl_testing.protocol.base import Protocol
from asl_testing.protocol.can import Can
from asl_testing.protocol.mil1553 import Mil1553
from asl_testing.protocol.stream import Ethernet, Header, Serial, Splitter

Address = tuple[str, int]                   # (UTS path, interface)

_DEFINED: list["Channel"] = []              # every channel of every ChannelSet, in definition order


def defined_channels() -> list["Channel"]:
    """Channels defined in a ChannelSet. On a polled address all of them take part in RX (the
    address's splitter and the order of the headers apply even if a channel has no RX message)."""
    return list(_DEFINED)


class Channel:
    def __init__(self, interface: int, protocol: Protocol, name: str = ""):
        self.interface = interface
        self.protocol = protocol
        self.name = name                    # set by ChannelSet
        self.registry = ChannelRegistry(self)

    @property
    def address(self) -> Address:
        return (self.protocol.path, self.interface)

    @property
    def has_header(self) -> bool:
        return getattr(self.protocol, "has_header", False)

    @property
    def splitter(self) -> Optional[Splitter]:
        return getattr(self.protocol, "splitter", None)

    def __str__(self) -> str:
        return self.name or f"{self.protocol.path}:{self.interface}"

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self}>"


class EthernetChannel(Channel):
    def __init__(self, interface: int, header: Optional[Header] = None, splitter: Optional[Splitter] = None):
        super().__init__(interface, Ethernet(header, splitter))


class Rs422Channel(Channel):
    def __init__(self, interface: int, header: Optional[Header] = None, splitter: Optional[Splitter] = None):
        super().__init__(interface, Serial(header, splitter))


class Mil1553Channel(Channel):
    """A 1553 bus; messages give node= and subnet=. byteorder: how the message bytes map to words."""

    def __init__(self, interface: int, byteorder: str = "big"):
        super().__init__(interface, Mil1553(byteorder))


class CanChannel(Channel):
    """A CAN bus; messages give can_id= (or _address). extended: 29-bit ids."""

    def __init__(self, interface: int, extended: bool = False):
        super().__init__(interface, Can(extended))


class ChannelSet:
    """The channels of a project: names them and checks the rules when the class is defined."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name, value in vars(cls).items():
            if isinstance(value, Channel):
                value.name = name
                if value not in _DEFINED:
                    _DEFINED.append(value)
        check_channels(cls.all())

    @classmethod
    def all(cls) -> Iterator[Channel]:
        for klass in reversed(cls.__mro__):
            for value in vars(klass).values():
                if isinstance(value, Channel):
                    yield value


def check_channels(channels: Iterable[Channel]) -> None:
    """On one address: one protocol type, at most one splitter and at most one channel whose protocol
    accepts every packet (no header), since their packets could not be told apart."""
    first: dict[Address, Channel] = {}
    takes_all: dict[Address, Channel] = {}
    split: dict[Address, Channel] = {}
    for ch in channels:
        other = first.setdefault(ch.address, ch)
        if type(other.protocol) is not type(ch.protocol):
            raise ValueError(f"{other} and {ch} share {ch.protocol.path}:{ch.interface} "
                             f"with different protocols ({other.protocol!r}, {ch.protocol!r})")
        if ch.protocol.accepts_all:
            if ch.address in takes_all:
                raise ValueError(f"{takes_all[ch.address]} and {ch} share {ch.protocol.path}:{ch.interface} "
                                 f"without a header; their packets could not be told apart")
            takes_all[ch.address] = ch
        if ch.splitter is not None:
            if ch.address in split:
                raise ValueError(f"{split[ch.address]} and {ch} both define a splitter for "
                                 f"{ch.protocol.path}:{ch.interface}; an address has one splitter")
            split[ch.address] = ch


def by_address(channels: Iterable[Channel]) -> dict[Address, list[Channel]]:
    """Groups channels by address, in the order they are tried on RX: with a header first, the one
    that accepts every packet last."""
    groups: dict[Address, list[Channel]] = {}
    for ch in channels:
        groups.setdefault(ch.address, []).append(ch)
    return {address: sorted(chans, key=lambda ch: ch.protocol.accepts_all) for address, chans in groups.items()}
