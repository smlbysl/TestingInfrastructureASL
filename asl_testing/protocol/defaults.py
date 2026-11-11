"""Which protocol object a channel type uses by default.

A type without a protocol object here (CAN today) still uses the old byte path (uts.transfer / uts.fetch).
"""
from asl_testing.channel.channel import ProtocolType
from asl_testing.protocol.base import Protocol
from asl_testing.protocol.ethernet import EthernetProtocol
from asl_testing.protocol.rs422 import Rs422Protocol


def default_protocols() -> dict[ProtocolType, Protocol]:
    return {ProtocolType.ETHERNET: EthernetProtocol(), ProtocolType.RS422: Rs422Protocol()}
