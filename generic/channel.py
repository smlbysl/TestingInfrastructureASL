"""Channel: the logical channel a message travels on.

A channel names the physical link it uses (links come from the setup file) and its envelope.
Several channels may share one link, e.g. one with an Ethernet header and one without.

Channels are defined once, in a project's ChannelSet; equality is identity.
Raw rules can be added at run time (e.g. by a test) and work on the message bytes:
    RX: line -> link splitter -> envelope.on_receive -> on_receive_raw rules -> dispatcher
    TX: msg.pack() -> on_send_raw rules -> envelope.on_send -> line
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Iterator, Optional

from generic.framing import Envelope

if TYPE_CHECKING:
    from comm.link import Link

RawRule = Callable[[bytes], Optional[bytes]]


class Channel:
    def __init__(self, link: str, envelope: Optional[Envelope] = None):
        self.link_name = link                       # name of the link in the setup file
        self.envelope = envelope if envelope is not None else Envelope()
        self.name = ""                              # set by ChannelSet
        self.link: Optional[Link] = None            # set by ChannelSet.bind
        self._rx_rules: list[RawRule] = []
        self._tx_rules: list[RawRule] = []

    @property
    def has_envelope(self) -> bool:
        return type(self.envelope) is not Envelope

    # ---------------------------------------------------------------- raw rules

    def on_receive_raw(self, rule: RawRule) -> RawRule:
        """rule(message bytes) -> bytes, or None to drop the packet. Runs in the RX thread."""
        self._rx_rules.append(rule)
        return rule

    def on_send_raw(self, rule: RawRule) -> RawRule:
        """rule(message bytes) -> bytes, applied before the envelope."""
        self._tx_rules.append(rule)
        return rule

    def apply_rx_rules(self, data: bytes) -> Optional[bytes]:
        for rule in list(self._rx_rules):
            data = rule(data)
            if data is None:
                return None
        return data

    def to_wire(self, data: bytes) -> bytes:
        for rule in list(self._tx_rules):
            data = rule(data)
        return self.envelope.on_send(data)

    def __str__(self) -> str:
        return self.name or f"Channel({self.link_name})"

    __repr__ = __str__


class ChannelSet:
    """The channels of a project, defined once as class attributes.

        class MyChannels(ChannelSet):
            CONTROL = Channel("SER1")
            DIAG    = Channel("ETH1", envelope=EthHeader())
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name, value in vars(cls).items():
            if isinstance(value, Channel):
                value.name = name

    @classmethod
    def all(cls) -> Iterator[Channel]:
        for klass in reversed(cls.__mro__):
            for value in vars(klass).values():
                if isinstance(value, Channel):
                    yield value

    @classmethod
    def bind(cls, links: dict[str, Link]) -> None:
        """Resolves link names and checks the channel set against the links of the setup."""
        plain: dict[str, str] = {}
        for ch in cls.all():
            if ch.link_name not in links:
                raise ValueError(f"channel {ch.name}: link '{ch.link_name}' is not in the setup "
                                 f"(links: {', '.join(links) or 'none'})")
            ch.link = links[ch.link_name]
            if not ch.has_envelope:
                if ch.link_name in plain:
                    raise ValueError(f"channels {plain[ch.link_name]} and {ch.name} both use link "
                                     f"{ch.link_name} without an envelope; a packet could not be told apart")
                plain[ch.link_name] = ch.name

    @classmethod
    def on_link(cls, link: Link) -> list[Channel]:
        """Channels of a link in the order they are tried on RX: with an envelope first, plain last."""
        chans = [ch for ch in cls.all() if ch.link is link]
        return sorted(chans, key=lambda ch: not ch.has_envelope)
