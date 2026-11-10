"""Which protocol object a channel type uses by default.

Only the types that have moved to a protocol object are listed; the others still use the old byte path.
"""
from asl_testing.channel.channel import ProtocolType
from asl_testing.protocol.base import Protocol
from asl_testing.protocol.ethernet import EthernetProtocol


def default_protocols() -> dict[ProtocolType, Protocol]:
    return {ProtocolType.ETHERNET: EthernetProtocol()}
