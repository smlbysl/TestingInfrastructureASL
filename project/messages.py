"""Mesaj tanımları (ICD). Mesaj sınıfı sadece payload alanlarını tanımlar."""
from ctypes import c_uint32

from project.project import Family1, Family2


class request(Family1):
    _fields_ = [
        ("request",     c_uint32 * 4),
    ]


class comut(Family1):
    _fields_ = [
        ("comut",       c_uint32 * 2),
    ]


class bambaşka(Family2):
    _fields_ = [
        ("request",     c_uint32 * 4),
    ]
