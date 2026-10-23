"""Proje ve aileleri.

ProjectBase (proje)  : endian, header, varsayılan channel/yön/periyot
 ├ Family1 (aile)    : signature = destinationId + messageId
 └ Family2 (aile)    : signature = destinationId + sourceId
"""
from ctypes import LittleEndianStructure, c_uint32

from generic.basemessage import BaseMessageStructure
from generic.enumerations import Direction, ProtocolType
from generic.signature import Signature
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

    # Varsayılan channel
    _COMMPROTOCOL_ = ProtocolType.RS422
    _COMMINTERFACE_ = 0

    # Varsayılan yön / periyot
    _DIRECTION_ = Direction.RX
    _PERIOD_ = None

    def __init__(self, sourceid, destinationid, messageid, **kw):
        # kw: channel, direction, rx_period, tx_period, rx_tolerance
        self.sourceId = sourceid
        self.destinationId = destinationid
        self.messageId = messageid
        super().__init__(**kw)


class Family1(ProjectBase):
    _signature = Signature("destinationId", "messageId")


class Family2(ProjectBase):
    _signature = Signature("destinationId", "sourceId")
