"""Message definitions (ICD). A message class defines its payload fields and ends with the checksum."""
from ctypes import c_uint16, c_uint32

from project.project import Family1, Family2
from project.types import CRC16


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
