"""MIL-STD-1553 protocol object: addresses, bytes <-> 16-bit words, byte order."""
import unittest
from ctypes import BigEndianStructure, LittleEndianStructure, c_uint16, c_uint32

from asl_testing import Mil1553Address, Mil1553Protocol


def message(base):
    class Msg(base):
        _pack_ = 1
        _fields_ = [("a", c_uint16), ("b", c_uint32)]
    return Msg(a=0xABCD, b=0x11223344)


class AddressTests(unittest.TestCase):
    def test_range_is_1_to_32(self):
        Mil1553Address(1, 1)
        Mil1553Address(32, 32)
        for rt, sa in ((0, 1), (33, 1), (1, 0), (1, 33), ("5", 1), (True, 1)):
            with self.subTest(rt=rt, sa=sa), self.assertRaises(ValueError):
                Mil1553Address(rt, sa)

    def test_equal_addresses_are_the_same_key(self):
        self.assertEqual(Mil1553Address(5, 3), Mil1553Address(5, 3))
        self.assertEqual(len({Mil1553Address(5, 3), Mil1553Address(5, 3)}), 1)
        self.assertEqual(str(Mil1553Address(5, 3)), "RT5/SA3")


class EncodeDecodeTests(unittest.TestCase):
    def test_encode_list(self):
        body = Mil1553Protocol().encode(b"\x01\x02\x03\x04", Mil1553Address(5, 3))
        self.assertEqual(body, {"message": [5, 3, 2, 0x0201, 0x0403]})

    def test_decode_list(self):
        received = Mil1553Protocol().decode({"message": [5, 3, 2, 0x0201, 0x0403], "timestamp": 7})
        self.assertEqual(received.data, b"\x01\x02\x03\x04")
        self.assertEqual(received.address, Mil1553Address(5, 3))
        self.assertEqual(received.timestamp, 7)

    def test_simulate_is_what_decode_reads(self):
        protocol = Mil1553Protocol(byte_order="big", time_unit=1e-6)
        received = protocol.decode(protocol.simulate(b"\xAA\xBB\xCC\xDD", 1.5, Mil1553Address(2, 30)))
        self.assertEqual((received.data, received.address), (b"\xAA\xBB\xCC\xDD", Mil1553Address(2, 30)))
        self.assertAlmostEqual(received.timestamp, 1.5)

    def test_encode_needs_an_address(self):
        with self.assertRaises(ValueError):
            Mil1553Protocol().encode(b"\x01\x02")

    def test_word_limits(self):
        protocol, address = Mil1553Protocol(), Mil1553Address(1, 1)
        self.assertEqual(protocol.encode(bytes(64), address)["message"][2], 32)
        for data in (b"", b"\x01", bytes(66)):              # no word, half a word, 33 words
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                protocol.encode(data, address)

    def test_malformed_items(self):
        protocol = Mil1553Protocol()
        for item in ({}, {"message": [1, 1]}, {"message": [0, 1, 1, 5]},
                     {"message": [1, 1, 2, 5]}, {"message": [1, 1, 1, 0x10000]}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                protocol.decode(item)


class ByteOrderTests(unittest.TestCase):
    """A 32-bit field is 2 words; byte_order has to match the structure's byte order."""

    def words(self, base, byte_order):
        return Mil1553Protocol(byte_order).encode(bytes(message(base)), Mil1553Address(1, 1))["message"][3:]

    def test_little_endian_structure(self):
        self.assertEqual(self.words(LittleEndianStructure, "little"), [0xABCD, 0x3344, 0x1122])   # low word first

    def test_big_endian_structure(self):
        self.assertEqual(self.words(BigEndianStructure, "big"), [0xABCD, 0x1122, 0x3344])         # high word first

    def test_mismatch_swaps_the_bytes_of_every_word(self):
        self.assertEqual(self.words(LittleEndianStructure, "big"), [0xCDAB, 0x4433, 0x2211])
        self.assertEqual(self.words(BigEndianStructure, "little"), [0xCDAB, 0x2211, 0x4433])

    def test_round_trip_keeps_the_values(self):
        for base, order in ((LittleEndianStructure, "little"), (BigEndianStructure, "big")):
            with self.subTest(base=base.__name__):
                protocol = Mil1553Protocol(order)
                original = message(base)
                data = protocol.decode(protocol.simulate(bytes(original), None, Mil1553Address(1, 1))).data
                copy = type(original).from_buffer_copy(data)
                self.assertEqual((copy.a, copy.b), (0xABCD, 0x11223344))


if __name__ == "__main__":
    unittest.main()
