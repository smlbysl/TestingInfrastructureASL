"""Projeye özel alan tipleri (generic.fieldtypes'tan türer)."""
from ctypes import c_char, c_uint16

from generic.fieldtypes import AsciiType, ChecksumType, CounterType, LengthType


class Length16(LengthType):
    _fields_ = [("value", c_uint16)]


class Counter8(CounterType):
    _fields_ = [("value", c_uint16)]

    def on_set(self, v) -> int:
        return v % 256


class CRC16(ChecksumType):
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
    _fields_ = [("value", c_char * 4)]


class AsciiChar(AsciiType):
    _fields_ = [("value", c_char)]
