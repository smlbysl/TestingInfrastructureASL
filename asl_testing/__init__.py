"""asl_testing: message model and UTS communication for test code.

Tests and project definitions import everything from here:

    from asl_testing import Comm, BaseMessageStructure, Timing, Direction, ChannelSet

Sub-packages (each uses only the ones below it):
    comm.py      Comm, the entry point
    services/    CSV log, error log, monitor
    runtime/     transport, RX poller, dispatcher, TX scheduler
    events/      event types, event bus
    adapter/     Adapter (what the core needs); adapter/uts: UtsAdapter, protocol definitions, fake
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

# protocol definitions of UTS (one class per protocol name)
from asl_testing.adapter.uts.protocols import EthernetProtocol, Mil1553Protocol, Protocol, Rs422Protocol

# events
from asl_testing.events.bus import EventBus, Subscriber
from asl_testing.events.types import (InvalidReceived, LinkError, MessageEvent, MessageReceived, MessageSent,
                                      RxOverflow, RxRestored, RxTimeout, UnknownReceived, WireReceived, WireSent)

# adapters
from asl_testing.adapter.base import Adapter, AdapterError, Polled, Received
from asl_testing.adapter.uts.adapter import UtsAdapter
from asl_testing.adapter.uts.fake import FakeUtsAdapter

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
    "UnknownReceived", "RxTimeout", "RxRestored", "RxOverflow", "LinkError", "WireReceived", "WireSent",
    "Adapter", "AdapterError", "Polled", "UtsAdapter", "FakeUtsAdapter",
    "ErrorLog", "CommLogger", "MonitorService",
]
