"""asl_testing: message model and UTS communication for test code.

Test code and project definitions import everything from this module:

    from asl_testing import Comm, BaseMessageStructure, Timing, Direction, Channel, ChannelSet

The sub-packages are the library's internals (layers, each importing only the ones below it):
    comm.py      Comm: the single entry point for test code
    services/    event subscribers (message history, error log, monitor)
    runtime/     transport, RX poller, dispatcher, TX scheduler
    events/      event types and the event bus
    uts/         UTS client (HTTP, fake), gateway adapters (PDU <-> UTS JSON), UTS control
    channel/     channel = interface + protocol + its message registry
    protocol/    PDU model (PCI + SDU) and the bus types (Ethernet, serial ...)
    message/     message model (base class, fields, signature, timing, state)
"""
__version__ = "2.1.dev4"

import sys as _sys


def _check_gil() -> None:
    """Consistent reads rely on the GIL (one-copy decode / snapshot); refuse a free-threaded build."""
    if hasattr(_sys, "_is_gil_enabled") and not _sys._is_gil_enabled():
        raise RuntimeError("asl_testing relies on the GIL for consistent message reads; "
                           "run it on a standard (GIL-enabled) CPython build")


_check_gil()

# comm first: it pulls in the layers below, the rest only re-exports names
from asl_testing.comm import Comm

# message model
from asl_testing.message.base import BaseMessageStructure
from asl_testing.message.fields import (AsciiType, ChecksumType, CounterType, FieldType, LengthType)
from asl_testing.message.history import MessageHistory, Record
from asl_testing.message.signature import Signature
from asl_testing.message.timing import Direction, Timing

# protocols and channels
from asl_testing.protocol.pdu import NO_PCI, NoPci, Pci, Pdu
from asl_testing.protocol.base import Protocol
from asl_testing.protocol.stream import ByteStream, Ethernet, Header, Serial, Splitter
from asl_testing.protocol.mil1553 import Mil1553, Mil1553Pci
from asl_testing.protocol.can import Can, CanPci
from asl_testing.channel.channel import (CanChannel, Channel, ChannelSet, EthernetChannel, Mil1553Channel,
                                         Rs422Channel)

# events
from asl_testing.events.bus import EventBus, Subscriber
from asl_testing.events.types import (InvalidReceived, LinkError, MessageEvent, MessageReceived, MessageSent,
                                      RxRestored, RxTimeout, UnknownReceived, WireReceived, WireSent)

# UTS
from asl_testing.uts.client import UtsClient, UtsError
from asl_testing.uts.adapters import (ByteListAdapter, CanAdapter, Mil1553Adapter, UtsAdapter, UtsFormatError,
                                     register_adapter)
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
    "Pci", "NoPci", "NO_PCI", "Pdu", "Protocol", "ByteStream", "Ethernet", "Serial", "Header", "Splitter",
    "Mil1553", "Mil1553Pci", "Can", "CanPci",
    "Channel", "ChannelSet", "EthernetChannel", "Rs422Channel", "Mil1553Channel", "CanChannel",
    "EventBus", "Subscriber", "MessageEvent", "MessageReceived", "MessageSent", "InvalidReceived",
    "UnknownReceived", "RxTimeout", "RxRestored", "LinkError", "WireReceived", "WireSent",
    "UtsClient", "UtsError", "UtsFormatError", "UtsAdapter", "ByteListAdapter", "Mil1553Adapter", "CanAdapter",
    "register_adapter",
    "UtsControl", "FakeUtsClient", "HttpUtsClient",
    "ErrorLog", "CommLogger", "MonitorService",
]
