"""Protocol objects: Ethernet and RS422 go through their protocol object (UTS post / get)."""

__author__ = "İsmail Baysal"

import time
import unittest

from asl_testing import Direction, EthernetProtocol, LinkError, Rs422Protocol
from projects.example_project.messages import bambaşka, comut
from tests.base import CommTestCase
from tests.settings import DEST, SRC


class Rs422ProtocolTests(unittest.TestCase):
    def test_encode_decode(self):
        protocol = Rs422Protocol(time_unit=1e-3)
        self.assertEqual(protocol.encode(b"\x01\x02"), {"message": [1, 2]})
        received = protocol.decode(protocol.simulate(b"\x01\x02", 1.5))
        self.assertEqual(received.data, b"\x01\x02")
        self.assertAlmostEqual(received.timestamp, 1.5)

    def test_path(self):
        self.assertEqual(Rs422Protocol.path, "rs422")


class EthernetProtocolTests(unittest.TestCase):
    def test_encode(self):
        self.assertEqual(EthernetProtocol().encode(b"\x01\x02"), {"message": [1, 2]})

    def test_decode(self):
        received = EthernetProtocol().decode({"message": [1, 2], "timestamp": 5})
        self.assertEqual((received.data, received.timestamp), (b"\x01\x02", 5))

    def test_time_unit(self):
        received = EthernetProtocol(time_unit=1e-6).decode({"message": [], "timestamp": 2_000_000})
        self.assertAlmostEqual(received.timestamp, 2.0)

    def test_simulate_is_what_decode_reads(self):
        protocol = EthernetProtocol(time_unit=1e-3)
        received = protocol.decode(protocol.simulate(b"\xAA\xBB", 1.5))
        self.assertEqual(received.data, b"\xAA\xBB")
        self.assertAlmostEqual(received.timestamp, 1.5)


class EthernetThroughCommTests(CommTestCase):
    def test_tx_goes_to_post(self):
        self.send(bambaşka(0x07, SRC, 0x40, direction=Direction.TX))          # DIAG: Ethernet with header
        path, interface, body = self.uts.posted[-1]
        self.assertEqual((path, interface), ("ethernet", 1))
        self.assertEqual(body["message"][:2], [0x55, 0xAA])                    # the header is on the line
        self.assertEqual(self.uts.sent, [])                                    # nothing on the byte level

    def test_rx_comes_from_get(self):
        rx = bambaşka(0x07, SRC, 0x40)
        rx.has_new()
        self.device_sends(bambaşka(0x07, SRC, 0x40, direction=Direction.TX, request=(5, 6, 7, 8)))
        self.expect_new(rx)
        self.assertEqual(list(rx.request), [5, 6, 7, 8])

    def test_rs422_goes_to_post(self):
        self.send(comut(SRC, DEST, 0x21, direction=Direction.TX))              # CONTROL: RS422
        path, interface, body = self.uts.posted[-1]
        self.assertEqual((path, interface), ("rs422", 0))
        self.assertTrue(comut(SRC, DEST, 0x21).validate(bytes(body["message"])))  # the packet, as a list of bytes
        self.assertEqual(self.uts.sent, [])                                    # nothing on the byte level

    def test_rs422_rx_comes_from_get(self):
        rx = comut(DEST, SRC, 0x20)
        rx.has_new()
        self.device_sends(comut(DEST, SRC, 0x20, direction=Direction.TX, comut=(7, 8)))
        self.expect_new(rx)
        self.assertEqual(list(rx.comut), [7, 8])

    def test_failed_post_is_a_failed_send(self):
        errors = []
        self.comm.subscribe(LinkError, errors.append)

        def unreachable(*args):
            raise ConnectionError("UTS unreachable")

        self.uts.post = unreachable
        msg = comut(SRC, DEST, 0x21, direction=Direction.TX)
        self.assertFalse(self.comm.send(msg))
        self.assertEqual(msg.peek_sent(), 0)                                   # not counted as sent
        deadline = time.monotonic() + self.timeout
        while not errors and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
