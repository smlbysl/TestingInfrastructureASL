"""asl_testing: message model and UTS communication for test code.

Tests and project definitions import everything from here:

    from asl_testing import Comm, BaseMessageStructure, Timing, Direction, ChannelSet

Sub-packages (each uses only the ones below it):
    comm.py      Comm, the entry point
    services/    CSV log, error log, monitor
    runtime/     transport, RX poller, dispatcher, TX scheduler
    events/      event types, event bus
    backend/     Backend contract, FakeBackend; backend/uts: UTS api, codecs, control
    channel/     channels, framing
    message/     message model
"""

__author__ = "İsmail Baysal"
__version__ = "2.1.dev6"

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

# events
from asl_testing.events.bus import EventBus, Subscriber
from asl_testing.events.types import (InvalidReceived, LinkError, MessageEvent, MessageReceived, MessageSent,
                                      RxOverflow, RxRestored, RxTimeout, UnknownReceived, WireReceived, WireSent)

# backends
from asl_testing.backend.base import Backend, BackendError, Received, Response
from asl_testing.backend.fake import FakeBackend
from asl_testing.backend.uts.api import UtsApi, WrapperUtsApi, uts_response
from asl_testing.backend.uts.backend import UtsBackend
from asl_testing.backend.uts.control import UtsControl
from asl_testing.backend.uts.fake import FakeUtsApi, FakeUtsBackend

# services
from asl_testing.services.errors import ErrorLog
from asl_testing.services.comm_logger import CommLogger
from asl_testing.services.monitor import MonitorService

__all__ = [
    "Comm", "BaseMessageStructure", "Signature", "Timing", "Direction",
    "FieldType", "LengthType", "CounterType", "ChecksumType", "AsciiType", "MessageHistory", "Record",
    "Channel", "ChannelSet", "EthernetChannel", "Rs422Channel", "Mil1553Channel",
    "Framing", "Envelope", "Splitter",
    "EventBus", "Subscriber", "MessageEvent", "MessageReceived", "MessageSent", "InvalidReceived",
    "UnknownReceived", "RxTimeout", "RxRestored", "RxOverflow", "LinkError", "WireReceived", "WireSent",
    "Backend", "BackendError", "Received", "Response", "FakeBackend",
    "UtsBackend", "UtsApi", "WrapperUtsApi", "uts_response", "UtsControl", "FakeUtsApi", "FakeUtsBackend",
    "ErrorLog", "CommLogger", "MonitorService",
]
