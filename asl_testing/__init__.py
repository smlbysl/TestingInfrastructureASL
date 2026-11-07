"""asl_testing: message model and UTS communication for test code.

Layers (each imports only the ones below it):
    comm.py      Comm: the single entry point for test code
    services/    event subscribers (message history, error log)
    runtime/     transport, RX poller, dispatcher, TX scheduler
    events/      event types and the event bus
    uts/         UTS client (HTTP, fake)
    channel/     channel definition and framing
    message/     message model (base class, fields, signature, registry)
"""
__version__ = "2.1.dev3"

from asl_testing.channel.channel import Channel, ChannelSet, EthernetChannel, ProtocolType, Rs422Channel
from asl_testing.channel.framing import Envelope, Framing, Splitter
from asl_testing.comm import Comm
from asl_testing.message.base import BaseMessageStructure
from asl_testing.message.signature import Signature
from asl_testing.message.timing import Direction, Timing
from asl_testing.uts.client import UtsClient, UtsFrame
from asl_testing.uts.fake import FakeUtsClient
from asl_testing.uts.http import HttpUtsClient
