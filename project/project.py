"""Project and its families.

ProjectBase (project)  : endianness, header, default channel/direction/timing
 ├ Family1 (family)    : signature = destinationId + messageId
 └ Family2 (family)    : signature = destinationId + sourceId
"""
from ctypes import LittleEndianStructure, c_uint32

from generic.basemessage import BaseMessageStructure
from generic.channel import Channel
from generic.enumerations import Direction, ProtocolType
from generic.signature import Signature
from generic.timing import Timing
from project.types import CRC16, Counter8, Length16


class ProjectBase(BaseMessageStructure, LittleEndianStructure):
    _fields_ = [
        ("ethHeader",       c_uint32 * 2),      # Ethernet header (not used in KOFIS)
        ("sourceId",        c_uint32),
        ("destinationId",   c_uint32),
        ("messageId",       c_uint32),
        ("messageLength",   Length16),
        ("messageCounter",  Counter8),
        ("checksum",        CRC16),
    ]

    # Defaults (overridden per object with channel= / direction= / rx= / tx=)
    _channel = Channel(ProtocolType.RS422, 0)
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
