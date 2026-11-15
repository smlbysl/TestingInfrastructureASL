"""Byte order given with endian=ENDIAN on the project base and on its field types."""

__author__ = "İsmail Baysal"

import unittest
from ctypes import BigEndianStructure, c_uint8, c_uint16

from asl_testing import BaseMessageStructure, ChecksumType, CounterType, FieldType
from projects.example_project.channels import MyChannels
from projects.example_project.types import Counter8

ENDIAN = "big"                                      # as in a project's settings.py


class BigCounter(CounterType, endian=ENDIAN):
    _fields_ = [("value", c_uint16)]


class BigCRC(ChecksumType, endian=ENDIAN):
    _fields_ = [("value", c_uint16)]

    def compute(self, data: bytes) -> int:
        return sum(data) & 0xFFFF


class BigBits(FieldType, endian=ENDIAN):
    _fields_ = [("flag", c_uint8, 1), ("mode", c_uint8, 3), ("spare", c_uint8, 4)]


class BigProject(BaseMessageStructure, endian=ENDIAN):
    _fields_ = [("cnt", BigCounter), ("x", c_uint16)]
    _channel = MyChannels.CONTROL


class big_msg(BigProject):                          # no keyword: keeps the project's byte order
    _fields_ = [("y", c_uint16), ("crc", BigCRC)]


class EndianTests(unittest.TestCase):
    def test_default_is_little(self):
        class Little(BaseMessageStructure):
            _fields_ = [("cnt", Counter8), ("x", c_uint16)]
            _channel = MyChannels.CONTROL
        msg = Little()
        msg.cnt.value, msg.x = 0x0102, 0x0304
        self.assertEqual(bytes(msg).hex(), "02010403")

    def test_big_message_and_field_types(self):
        msg = big_msg()
        msg.cnt.value, msg.x, msg.y = 0x0102, 0x0304, 0x0506
        self.assertEqual(bytes(msg)[:6].hex(), "010203040506")

    def test_subclass_keeps_the_byte_order(self):
        self.assertTrue(issubclass(big_msg, BigEndianStructure))
        self.assertIsInstance(big_msg().cnt, BigCounter)

    def test_pack_and_validate(self):
        msg = big_msg()
        msg.x = 0x0304
        raw, _ = msg._pack()
        self.assertEqual(raw[-2:], sum(raw[:-2]).to_bytes(2, "big"))
        self.assertTrue(big_msg().validate(raw))

    def test_bit_fields_start_from_the_high_bit(self):
        class WithBits(BigProject):
            _fields_ = [("bits", BigBits)]
        msg = WithBits()
        msg.bits.flag = 1
        self.assertEqual(bytes(msg)[-1:].hex(), "80")

    def test_field_type_of_the_other_byte_order_is_an_error(self):     # K3
        with self.assertRaises(TypeError):
            class Mixed(BaseMessageStructure, endian=ENDIAN):
                _fields_ = [("cnt", Counter8)]                         # little


if __name__ == "__main__":
    unittest.main()
