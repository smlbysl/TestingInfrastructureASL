"""Project and its families.

ProjectBase   byte order, header, default channel / direction / timing
 ├ Family1    signature destinationId + messageId
 ├ Family2    signature destinationId + sourceId
 └ Serial2    no signature: found by channel (one RX message per channel)

The checksum is not in the header; every message adds it as its last field.
"""

__author__ = "İsmail Baysal"
from ctypes import LittleEndianStructure, c_uint32

from asl_testing import BaseMessageStructure, Direction, Signature, Timing
from projects.example_project.channels import MyChannels
from projects.example_project.types import Counter8, Length16


class ProjectBase(BaseMessageStructure, LittleEndianStructure):
    _fields_ = [
        ("sourceId",        c_uint32),
        ("destinationId",   c_uint32),
        ("messageId",       c_uint32),
        ("messageLength",   Length16),
        ("messageCounter",  Counter8),
    ]

    # Defaults; an object can override them with channel= / direction= / rx= / tx=.
    _channel = MyChannels.CONTROL
    _direction = Direction.RX
    _timing = Timing()                  # event

    def __init__(self, sourceid, destinationid, messageid, **kw):
        self.sourceId = sourceid
        self.destinationId = destinationid
        self.messageId = messageid
        super().__init__(**kw)


class Family1(ProjectBase):
    _signature = Signature("destinationId", "messageId")


class Family2(ProjectBase):
    _signature = Signature("destinationId", "sourceId")
    _channel = MyChannels.DIAG                  # Ethernet with a header


class Serial2(ProjectBase):
    """Device on SER2 without an identifying field: `_signature = None`, found by channel."""
    _signature = None
    _channel = MyChannels.SER2
