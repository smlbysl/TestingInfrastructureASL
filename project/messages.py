"""Message definitions (ICD). A message class only defines its payload fields."""
from ctypes import c_uint32

from project.project import Family1, Family2


class request(Family1):
    _fields_ = [
        ("request",     c_uint32 * 4),
    ]
    _defaults = {"request": (0, 0xA1, 0xA2, 0xA3)}


class comut(Family1):
    _fields_ = [
        ("comut",       c_uint32 * 2),
    ]


class bambaşka(Family2):
    _fields_ = [
        ("request",     c_uint32 * 4),
    ]
