"""asl_testing: message model and UTS communication for test code.

Tests and project definitions import everything from here:

    from asl_testing import Comm, BaseMessageStructure, Timing, Direction, ChannelSet

Sub-packages (each uses only the ones below it):
    comm.py      Comm, the entry point
    services/    CSV log, error log, monitor
    runtime/     transport, RX poller, dispatcher, TX scheduler
    events/      event types, event bus
    uts/         UTS client (HTTP, fake), UTS control
    protocol/    protocol objects (Ethernet, RS422, MIL-STD-1553)
    channel/     channels, framing
    message/     message model
"""

__author__ = "İsmail Baysal"
__version__ = "2.1.dev3"

# comm first: it imports the layers below; the rest only re-exports names
from asl_testing.comm import Comm

# message model
from asl_testing.message.base import BaseMessageStructure
from asl_testing.message.fields import (AsciiType, ChecksumType, CounterType, FieldType, LengthType)
from asl_testing.message.history import MessageHistory, Record
from asl_testing.message.signature import Signature
from asl_testing.message.timing import Direction, Timing

# channels and framing
from asl_testing.channel.channel import Channel, ChannelSet, EthernetChannel, Mil1553Channel, Rs422Channel
from asl_testing.channel.framing import Envelope, Framing, Splitter

# protocols (one class per bus type)
from asl_testing.protocol.base import Protocol, Received
from asl_testing.protocol.ethernet import EthernetProtocol
from asl_testing.protocol.mil1553 import Mil1553Protocol
from asl_testing.protocol.rs422 import Rs422Protocol

# events
from asl_testing.events.bus import EventBus, Subscriber
from asl_testing.events.types import (InvalidReceived, LinkError, MessageEvent, MessageReceived, MessageSent,
                                      RxRestored, RxTimeout, UnknownReceived, WireReceived, WireSent)

# UTS
from asl_testing.uts.client import UtsClient, UtsError
from asl_testing.uts.control import UtsControl
from asl_testing.uts.fake import FakeUtsClient
from asl_testing.uts.http import HttpUtsClient

# services
from asl_testing.services.errors import ErrorLog
from asl_testing.services.comm_logger import CommLogger
from asl_testing.services.monitor import MonitorService

__all__ = [
    "Comm", "BaseMessageStructure", "Signature", "Timing", "Direction",
    "FieldType", "LengthType", "CounterType", "ChecksumType", "AsciiType", "MessageHistory", "Record",
    "Channel", "ChannelSet", "EthernetChannel", "Rs422Channel", "Mil1553Channel",
    "Framing", "Envelope", "Splitter", "Protocol", "Received", "EthernetProtocol", "Rs422Protocol", "Mil1553Protocol",
    "EventBus", "Subscriber", "MessageEvent", "MessageReceived", "MessageSent", "InvalidReceived",
    "UnknownReceived", "RxTimeout", "RxRestored", "LinkError", "WireReceived", "WireSent",
    "UtsClient", "UtsError", "UtsControl", "FakeUtsClient", "HttpUtsClient",
    "ErrorLog", "CommLogger", "MonitorService",
]
