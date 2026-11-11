"""Default protocol object of each channel type.

A type without one (CAN) uses the byte-level UTS calls (uts.transfer / uts.fetch).
"""

__author__ = "İsmail Baysal"

from asl_testing.channel.channel import ProtocolType
from asl_testing.protocol.base import Protocol
from asl_testing.protocol.ethernet import EthernetProtocol
from asl_testing.protocol.mil1553 import Mil1553Protocol
from asl_testing.protocol.rs422 import Rs422Protocol


def default_protocols() -> dict[ProtocolType, Protocol]:
    return {ProtocolType.ETHERNET: EthernetProtocol(), ProtocolType.RS422: Rs422Protocol(),
            ProtocolType.MIL1553: Mil1553Protocol()}
