"""MIL-STD-1553 protocol: the packet goes to and comes from UTS as [rt, subnet, word_count, word, ...]."""
import time
import unittest
from ctypes import BigEndianStructure, LittleEndianStructure, c_uint16, c_uint32

from asl_testing import (BaseMessageStructure, ChannelSet, Comm, Direction, FakeUtsClient, Mil1553Channel,
                         Mil1553Protocol, Signature)


def packet_type(base):
    class Packet(base):
        _pack_ = 1
        _fields_ = [("rt", c_uint16), ("subnet", c_uint16), ("wordCount", c_uint16),
                    ("mode", c_uint16), ("speed", c_uint32)]
    return Packet(rt=30, subnet=1, wordCount=3, mode=0x0001, speed=0x11223344)


class ListFormatTests(unittest.TestCase):
    def test_header_values_are_written_as_they_are(self):
        body = Mil1553Protocol("little").encode(bytes(packet_type(LittleEndianStructure)))
        self.assertEqual(body, {"message": [30, 1, 3, 0x0001, 0x3344, 0x1122]})

    def test_big_endian_structure_sends_the_high_word_first(self):
        body = Mil1553Protocol("big").encode(bytes(packet_type(BigEndianStructure)))
        self.assertEqual(body, {"message": [30, 1, 3, 0x0001, 0x1122, 0x3344]})

    def test_byte_order_not_matching_the_structure_swaps_every_value(self):
        body = Mil1553Protocol("big").encode(bytes(packet_type(LittleEndianStructure)))
        self.assertEqual(body["message"][:3], [7680, 256, 768])

    def test_decode_gives_the_message_bytes_back(self):
        for base, order in ((LittleEndianStructure, "little"), (BigEndianStructure, "big")):
            with self.subTest(base=base.__name__):
                original = packet_type(base)
                received = Mil1553Protocol(order).decode({"message": Mil1553Protocol(order).to_words(bytes(original)),
                                                          "timestamp": 2})
                copy = type(original).from_buffer_copy(received.data)
                self.assertEqual((copy.rt, copy.subnet, copy.wordCount, copy.mode, copy.speed),
                                 (30, 1, 3, 0x0001, 0x11223344))
                self.assertEqual(received.timestamp, 2)

    def test_time_unit(self):
        protocol = Mil1553Protocol(time_unit=1e-6)
        self.assertAlmostEqual(protocol.decode(protocol.simulate(b"\x01\x00", 1.5)).timestamp, 1.5)

    def test_byte_order_is_little_or_big(self):
        with self.assertRaises(ValueError):
            Mil1553Protocol("middle")


# A small 1553 project, defined here so the example project stays as it is.
class Bus(ChannelSet):
    A = Mil1553Channel(1)


class Project1553(BaseMessageStructure, LittleEndianStructure):
    _fields_ = [("rt", c_uint16), ("subnet", c_uint16), ("wordCount", c_uint16)]
    _signature = Signature("rt", "subnet")
    _channel = Bus.A

    def __init__(self, rt, subnet, **kw):
        self.rt, self.subnet = rt, subnet
        super().__init__(**kw)


class rt30_status(Project1553):
    _fields_ = [("mode", c_uint16), ("speed", c_uint32)]
    _defaults = {"wordCount": 3}


class ThroughCommTests(unittest.TestCase):
    def setUp(self):
        Project1553.clear_registry()
        self.uts = FakeUtsClient()
        self.comm = Comm(self.uts, [Project1553])
        self.comm.open()
        self.addCleanup(self.comm.close)

    def uts_item(self, item: dict) -> None:
        """Puts an item into the fake UTS exactly as UTS would return it."""
        with self.uts._lock:
            self.uts._items[("mil1553", Bus.A.interface)].append(item)

    def test_send_posts_the_list(self):
        msg = rt30_status(30, 1, direction=Direction.TX, mode=1, speed=0x11223344)
        self.assertTrue(self.comm.send(msg))
        self.assertEqual(self.uts.posted[-1], ("mil1553", 1, {"message": [30, 1, 3, 0x0001, 0x3344, 0x1122]}))

    def test_received_list_reaches_the_message(self):
        status = rt30_status(30, 1)
        other = rt30_status(30, 2)                          # same rt, other subnet: told apart by the signature
        status.has_new()
        self.uts_item({"message": [30, 1, 3, 0x0002, 0x0010, 0x0000], "timestamp": 5})
        self.assertEqual(self.comm.wait_new(status, timeout=1.0), 1)
        self.assertEqual((status.mode, status.speed, status.rx_timestamp), (2, 0x10, 5))
        self.assertEqual(other.peek_new(), 0)

    def test_inject_from_a_message(self):
        status = rt30_status(30, 1)
        device = rt30_status(30, 1, direction=Direction.TX, mode=7)
        status.has_new()
        self.uts.inject(Bus.A.protocol, Bus.A.interface, device.pack())
        self.assertEqual(self.comm.wait_new(status, timeout=1.0), 1)
        self.assertEqual(status.mode, 7)

    def test_unknown_subnet_is_unknown(self):
        rt30_status(30, 1)
        self.uts_item({"message": [30, 9, 3, 0, 0, 0]})
        deadline = time.monotonic() + 1.0
        while not self.comm.unknown and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(self.comm.unknown), 1)


if __name__ == "__main__":
    unittest.main()
