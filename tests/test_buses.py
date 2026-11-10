"""MIL-STD-1553 and CAN through the fake UTS: UTS bodies, identification by PCI, rules at definition."""
import time
import unittest

from asl_testing import Direction, LinkError, UnknownReceived
from projects.example_project.buses import (bit_report, brake_cmd, mode_a, mode_b, motor_demand, wheel_speed)
from projects.example_project.channels import MyChannels
from tests.base import CommTestCase


def wait_until(condition, timeout=1.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.005)
    return condition()


class Mil1553Tests(CommTestCase):
    def test_tx_body_is_node_subnet_count_words(self):
        self.send(motor_demand(node=5, subnet=1, speed=-300))
        path, interface, body = self.uts.sent[-1]
        self.assertEqual((path, interface), ("1553", 1))
        self.assertEqual(body["message"], [5, 1, 1, (-300) & 0xFFFF])

    def test_rx_identified_by_node_and_subnet(self):
        on_3, on_4 = bit_report(node=5, subnet=3), bit_report(node=5, subnet=4)
        self.uts.inject("1553", 1, {"message": [5, 3, 2, 0x0001, 0xFFF6]})
        self.uts.inject("1553", 1, {"message": [5, 4, 2, 0x0002, 0x0010]})
        self.assertTrue(wait_until(lambda: on_3.rx_state.count and on_4.rx_state.count))
        self.assertEqual((on_3.status, on_3.temperature), (1, -10))
        self.assertEqual((on_4.status, on_4.temperature), (2, 16))

    def test_signature_inside_the_words(self):
        a, b = mode_a(node=6, subnet=1), mode_b(node=6, subnet=1)
        unknown = []
        self.comm.subscribe(UnknownReceived, unknown.append)
        self.uts.inject("1553", 1, {"message": [6, 1, 2, 1, 111]})
        self.uts.inject("1553", 1, {"message": [6, 1, 2, 2, 222]})
        self.uts.inject("1553", 1, {"message": [6, 1, 2, 3, 333]})
        self.assertTrue(wait_until(lambda: a.rx_state.count and b.rx_state.count and unknown))
        self.assertEqual((a.value, b.value), (111, 222))
        self.assertEqual(str(unknown[0].pci), "node=6 subnet=1")

    def test_device_sends_round_trip(self):
        rx = bit_report(node=7, subnet=2)
        mark = rx.rx_history.mark()
        self.uts.device_sends(bit_report(node=7, subnet=2, direction=Direction.TX, status=9, temperature=-1))
        rec = self.comm.wait_for(rx, lambda s: s.status == 9, after=mark)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.snapshot().temperature, -1)

    def test_word_count_mismatch_is_a_link_error(self):
        errors = []
        self.comm.subscribe(LinkError, errors.append)
        bit_report(node=5, subnet=3)
        self.uts.inject("1553", 1, {"message": [5, 3, 3, 1, 2]})
        self.assertTrue(wait_until(lambda: errors))

    def test_address_is_mandatory_and_checked(self):
        with self.assertRaises(TypeError):
            bit_report(node=5)
        with self.assertRaises(ValueError):
            bit_report(node=33, subnet=1)


class CanTests(CommTestCase):
    def test_tx_body_has_the_id(self):
        self.send(brake_cmd(pressure=0x0102))
        path, interface, body = self.uts.sent[-1]
        self.assertEqual((path, interface, body["id"], body["message"]), ("can", 0, 0x200, [0x02, 0x01]))

    def test_rx_identified_by_id(self):
        whl = wheel_speed()
        self.uts.inject("can", 0, {"id": 0x123, "message": [0x84, 0x03, 1]})
        self.uts.inject("can", 0, {"id": 0x124, "message": [0, 0, 0]})          # no message: unknown
        self.assertTrue(wait_until(lambda: whl.rx_state.count))
        self.assertEqual((whl.rpm, whl.valid), (900, 1))
        self.assertTrue(wait_until(lambda: any(str(f.pdu.pci) == "can_id=292" for f in self.comm.unknown)))

    def test_more_than_8_bytes_is_a_definition_error(self):
        from ctypes import c_uint32
        from projects.example_project.buses import CanBase

        class too_big(CanBase):
            _address = {"can_id": 0x10}
            _fields_ = [("a", c_uint32), ("b", c_uint32), ("c", c_uint32)]

        with self.assertRaises(ValueError):
            too_big()

    def test_id_range(self):
        with self.assertRaises(ValueError):
            wheel_speed(can_id=0x800)


class ChannelRuleTests(unittest.TestCase):
    def test_bus_channels_are_named(self):
        self.assertEqual((str(MyChannels.BUS_A), MyChannels.BUS_A.address), ("BUS_A", ("1553", 1)))
        self.assertEqual(MyChannels.CAN0.address, ("can", 0))


if __name__ == "__main__":
    unittest.main()
