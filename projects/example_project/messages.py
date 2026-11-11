"""Message definitions (ICD). A message class defines its payload fields and ends with the checksum."""

__author__ = "İsmail Baysal"

from ctypes import c_int16, c_uint16, c_uint32

from asl_testing import Direction
from projects.example_project.header import Family1, Family2, Serial2
from projects.example_project.types import CRC16, CmdByte


class request(Family1):
    _fields_ = [
        ("request",     c_uint32 * 4),
        ("checksum",    CRC16),
    ]
    _defaults = {"request": (0, 0xA1, 0xA2, 0xA3)}


class comut(Family1):
    _fields_ = [
        ("comut",       c_uint32 * 2),
        ("checksum",    CRC16),
    ]


class bambaşka(Family2):
    _fields_ = [
        ("request",     c_uint32 * 4),
        ("checksum",    CRC16),
    ]


class diag_log(Family1):
    """Variable size: up to 16 entries; the real size is in messageLength."""
    _fields_ = [
        ("count",       c_uint16),
        ("entries",     c_uint32 * 16),
        ("checksum",    CRC16),
    ]
    _variable_size = True

    def body_size(self) -> int:                 # used for TX only; RX reads the size from the packet
        return diag_log.entries.offset + self.count * 4


class motor_cmd(Family1):
    """Command bits in one byte (CmdByte): the start request goes out once."""
    _fields_ = [
        ("cmd",         CmdByte),
        ("speed",       c_int16),
        ("checksum",    CRC16),
    ]


class ser_cmd(Serial2):
    """Outgoing on SER2."""
    _fields_ = [
        ("command",     c_uint16),
        ("checksum",    CRC16),
    ]
    _direction = Direction.TX


class ser_report(Serial2):
    """Incoming on SER2, variable size: the only RX message of the channel, so no signature is needed."""
    _fields_ = [
        ("count",       c_uint16),
        ("values",      c_uint16 * 8),
        ("checksum",    CRC16),
    ]
    _variable_size = True

    def body_size(self) -> int:
        return ser_report.values.offset + self.count * 2
