"""Channel: the protocol + interface a message travels on.

UTS is queried and addressed per protocol and interface; the pair is a channel.
Hashable, so it is used in the dispatch key.
"""
from dataclasses import dataclass

from generic.enumerations import ProtocolType


@dataclass(frozen=True)
class Channel:
    protocol: ProtocolType
    interface: int

    def __str__(self) -> str:
        return f"{self.protocol.name}:{self.interface}"
