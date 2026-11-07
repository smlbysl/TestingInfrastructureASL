"""Project and its families.

ProjectBase (project)  : endianness, header, default channel/direction/timing
 ├ Family1 (family)    : signature = destinationId + messageId
 ├ Family2 (family)    : signature = destinationId + sourceId
 └ Serial2 (family)    : no signature -> identified by its channel (one RX message per channel)

The checksum is not part of the header: every message adds it as its last field.
"""
from ctypes import LittleEndianStructure, c_uint32

from asl_testing.message.base import BaseMessageStructure
from asl_testing.message.timing import Direction
from asl_testing.message.signature import Signature
from asl_testing.message.timing import Timing
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

    # Defaults (overridden per object with channel= / direction= / rx= / tx=)
    _channel = MyChannels.CONTROL
    _direction = Direction.RX
    _timing = Timing()                  # event

    def __init__(self, sourceid, destinationid, messageid, **kw):
        # kw: channel, direction, rx, tx and field values
        self.sourceId = sourceid
        self.destinationId = destinationid
        self.messageId = messageid
        super().__init__(**kw)


class Family1(ProjectBase):
    _signature = Signature("destinationId", "messageId")


class Family2(ProjectBase):
    _signature = Signature("destinationId", "sourceId")
    _channel = MyChannels.DIAG                  # this family travels on Ethernet with a header


class Serial2(ProjectBase):
    """A device on SER2 whose packets carry no identifying field: the channel identifies the RX message.

    _signature = None opens a family of its own without a signature (key: channel, None).
    """
    _signature = None
    _channel = MyChannels.SER2
