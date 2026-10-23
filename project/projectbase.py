from ctypes import c_uint16, c_uint32, LittleEndianStructure, c_char
from typing import Optional

from generic.basemessage import BaseFooter, BaseMessageStructure, LengthType, CounterType, AsciiType, ChecksumType
from generic.signature import SignatureClass
from generic.enumerations import Direction, ProtocolType


class Length16(LengthType):
    _fields_ = [
        ("value", c_uint16)
    ]


class Counter8(CounterType):
    _fields_ = [
        ("value", c_uint16)
    ]

    def on_set(self, v) -> int:
        return v % 256


class CRC16(ChecksumType):
    _pack_ = 1
    _fields_ = [("value", c_uint16)]

    def compute(self, data: bytes) -> int:
        crc = 0xFFFF
        for b in data:
            crc ^= b << 8
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
                crc &= 0xFFFF
        return crc


class Ascii4(AsciiType):
    _fields_ = [
        ("value", c_char * 4)
    ]


class AsciiChar(AsciiType):
    _fields_ = [
        ("value", c_char)
    ]


signaturefields = ["destinationId", "messageId"]
projectsignature = SignatureClass(*signaturefields)


class ProjectBase1(BaseMessageStructure, LittleEndianStructure):
    _signature = projectsignature
    _fields_ = [
        ("ethHeader",       c_uint32*2),        # Ethernet header (not used in KOFIS)
        ("sourceId",        c_uint32),
        ("destinationId",   c_uint32),
        ("messageId",       c_uint32),
        ("messageLength",   Length16),
        ("messageCounter",  Counter8),
        ("checksum",        CRC16),
    ]

    #Communicatin Fields
    _COMMPROTOCOL_: Optional[ProtocolType] = ProtocolType.RS422
    _COMMINTERFACE_ = 0

    #Message Data
    _DIRECTION_ = Direction.RX
    _PERIOD_ = None

    def __init__(self, sourceid, destionationid, messageid):
        setattr(self, "sourceId", sourceid)
        setattr(self, "destinationId", destionationid)
        setattr(self, "messageId", messageid)

        super().__init__()


signaturefields2 = ["destinationId", "sourceId"]
projectsignature2 = SignatureClass(*signaturefields2)


class ProjectBase2(BaseMessageStructure, LittleEndianStructure):
    _signature = projectsignature2
    _fields_ = [
        ("ethHeader",       c_uint32*2),        # Ethernet header (not used in KOFIS)
        ("sourceId",        c_uint32),
        ("destinationId",   c_uint32),
        ("messageId",       c_uint32),
        ("messageLength",   Length16),
        ("messageCounter",  Counter8),
        ("checksum",        CRC16),
    ]

    #Communicatin Fields
    _COMMPROTOCOL_: Optional[ProtocolType] = ProtocolType.RS422
    _COMMINTERFACE_ = 0

    #Message Data
    _DIRECTION_ = Direction.RX
    _PERIOD_ = None

    def __init__(self, sourceid, destionationid, messageid):
        setattr(self, "sourceId", sourceid)
        setattr(self, "destinationId", destionationid)
        setattr(self, "messageId", messageid)

        super().__init__()


class bambaşka(ProjectBase2):
    _fields_ = [
        ("request",     c_uint32*4),
    ]


class request(ProjectBase1):
    _fields_ = [
        ("request",     c_uint32*4),
    ]
    x: list[int] = [1, 2, 3]


class comut(ProjectBase1):
    _fields_ = [
        ("comut",       c_uint32*2),
    ]


if __name__ == "__main__":
    src, dest = 0x0001, 0x0002

    request_swversion = request(src, dest, 0x10)
    request2_temp     = request(src, dest, 0x11)
    comut2            = comut(src, dest, 0x20)

    message1 = ProjectBase1(0xAABB, 0xCCDD, 0xDDEE)

    for m in (request_swversion, request2_temp, comut2, message1):
        print(f"{type(m).__name__:12} sig=0x{m.signature_id:X} "
              f"len={m.messageLength.val} crc=0x{m.checksum.val:04X} "
              f"bytes={bytes(m).hex()}")

    raw = bytes(comut2)
    found = ProjectBase1.Lookup(raw)
    print("Lookup ->", found.__name__ if found else None)
