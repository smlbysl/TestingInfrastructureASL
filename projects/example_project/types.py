"""Project-specific field types (derived from asl_testing.message.fields)."""
from ctypes import c_char, c_uint8, c_uint16

from asl_testing.message.fields import AsciiType, ChecksumType, CounterType, FieldType, LengthType


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


class CmdByte(FieldType):
    """One command byte whose bits are managed together.

    startReq goes out once and is cleared after a successful send; the other bits keep their value.
    Access: msg.cmd.startReq, msg.cmd.mode (no .val: the type has no single value field).
    """
    _fields_ = [
        ("startReq",  c_uint8, 1),
        ("mode",      c_uint8, 3),
        ("reserved",  c_uint8, 4),
    ]

    def on_init(self, msg) -> None:     # initial values (also restored by msg.initialize())
        self.startReq = 0
        self.mode = 1

    def after_send(self, msg) -> None:
        self.startReq = 0
