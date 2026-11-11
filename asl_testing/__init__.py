"""asl_testing: message model and UTS communication for test code.

Test code and project definitions import everything from this module:

    from asl_testing import Comm, BaseMessageStructure, Timing, Direction, Channel, ChannelSet

The sub-packages are the library's internals (layers, each importing only the ones below it):
    comm.py      Comm: the single entry point for test code
    services/    event subscribers (message history, error log, monitor)
    runtime/     transport, RX poller, dispatcher, TX scheduler
    events/      event types and the event bus
    uts/         UTS client (HTTP, fake) and UTS control
    channel/     channel definition and framing
    message/     message model (base class, fields, signature, registry, timing, state, history)
"""
__version__ = "2.1.dev3"

# comm first: it pulls in the layers below, the rest only re-exports names
from asl_testing.comm import Comm

# message model
from asl_testing.message.base import BaseMessageStructure
from asl_testing.message.fields import (AsciiType, ChecksumType, CounterType, FieldType, LengthType)
from asl_testing.message.history import MessageHistory, Record
from asl_testing.message.signature import Signature
from asl_testing.message.timing import Direction, Timing

# channels and framing
from asl_testing.channel.channel import Channel, ChannelSet, EthernetChannel, ProtocolType, Rs422Channel
from asl_testing.channel.framing import Envelope, Framing, Splitter

# events
from asl_testing.events.bus import EventBus, Subscriber
from asl_testing.events.types import (InvalidReceived, LinkError, MessageEvent, MessageReceived, MessageSent,
                                      RxRestored, RxTimeout, UnknownReceived, WireReceived, WireSent)

# UTS
from asl_testing.uts.client import UtsClient, UtsError, UtsFrame
from asl_testing.uts.control import UtsControl
from asl_testing.uts.fake import FakeUtsClient
from asl_testing.uts.http import HttpUtsClient

# services
from asl_testing.services.errors import ErrorLog
from asl_testing.services.history import CommLogger
from asl_testing.services.monitor import MonitorService

__all__ = [
    "Comm", "BaseMessageStructure", "Signature", "Timing", "Direction",
    "FieldType", "LengthType", "CounterType", "ChecksumType", "AsciiType", "MessageHistory", "Record",
    "Channel", "ChannelSet", "EthernetChannel", "Rs422Channel", "ProtocolType",
    "Framing", "Envelope", "Splitter",
    "EventBus", "Subscriber", "MessageEvent", "MessageReceived", "MessageSent", "InvalidReceived",
    "UnknownReceived", "RxTimeout", "RxRestored", "LinkError", "WireReceived", "WireSent",
    "UtsClient", "UtsError", "UtsFrame", "UtsControl", "FakeUtsClient", "HttpUtsClient",
    "ErrorLog", "CommLogger", "MonitorService",
]
