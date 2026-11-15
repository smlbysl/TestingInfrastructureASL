"""Protocol definitions of the UTS adapter: Ethernet and RS422 (UTS post / get)."""

__author__ = "İsmail Baysal"

import time
import unittest

from asl_testing import (Direction, EthernetChannel, EthernetProtocol, FakeUtsAdapter, LinkError, Rs422Channel,
                         Rs422Protocol, UnknownReceived, AdapterError)
from projects.example_project.channels import MyChannels
from projects.example_project.messages import bambaşka, comut
from tests.base import CommTestCase
from tests.settings import DEST, SRC


SER, ETH = Rs422Channel(0), EthernetChannel(1)


class Rs422ProtocolTests(unittest.TestCase):
    def test_encode_decode(self):
        protocol = Rs422Protocol(time_unit=1e-3)
        self.assertEqual(protocol.encode(SER, b"\x01\x02"), {"message": [1, 2]})
        received = protocol.decode(SER, protocol.simulate(SER, b"\x01\x02", 1.5))
        self.assertEqual(received.data, b"\x01\x02")
        self.assertAlmostEqual(received.timestamp, 1.5)

    def test_path(self):
        self.assertEqual(Rs422Protocol.path, "serials")


class EthernetProtocolTests(unittest.TestCase):
    def test_encode(self):
        self.assertEqual(EthernetProtocol().encode(ETH, b"\x01\x02"), {"message": [1, 2]})

    def test_decode(self):
        received = EthernetProtocol().decode(ETH, {"message": [1, 2], "timestamp": 5})
        self.assertEqual((received.data, received.timestamp), (b"\x01\x02", 5))

    def test_time_unit(self):
        received = EthernetProtocol(time_unit=1e-6).decode(ETH, {"message": [], "timestamp": 2_000_000})
        self.assertAlmostEqual(received.timestamp, 2.0)

    def test_simulate_is_what_decode_reads(self):
        protocol = EthernetProtocol(time_unit=1e-3)
        received = protocol.decode(ETH, protocol.simulate(ETH, b"\xAA\xBB", 1.5))
        self.assertEqual(received.data, b"\xAA\xBB")
        self.assertAlmostEqual(received.timestamp, 1.5)


class AdapterProtocolTests(unittest.TestCase):
    def test_adapter_finds_the_definition_by_the_channel_protocol(self):
        adapter = FakeUtsAdapter()
        self.assertIsInstance(adapter.protocol(SER), Rs422Protocol)
        self.assertIsInstance(adapter.protocol(ETH), EthernetProtocol)

    def test_time_unit_of_the_adapter_reaches_every_definition(self):
        adapter = FakeUtsAdapter(time_unit=1e-6)
        self.assertEqual({p.time_unit for p in adapter.protocols.values()}, {1e-6})

    def test_timeout_of_each_protocol(self):
        adapter = FakeUtsAdapter()
        self.assertEqual({name: adapter.timeout_of(p) for name, p in adapter.protocols.items()},
                         {"ethernet": 2.0, "rs422": 3.0, "mil1553": 2.0})

    def test_timeout_given_to_the_adapter_is_used_for_every_protocol(self):
        adapter = FakeUtsAdapter(timeout=0.5)
        self.assertEqual({adapter.timeout_of(p) for p in adapter.protocols.values()}, {0.5})

    def test_every_request_gets_the_timeout(self):
        class RecordingAdapter(FakeUtsAdapter):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.timeouts = []

            def post(self, path, interface, body, timeout=0.0):
                self.timeouts.append(("POST", path, timeout))
                super().post(path, interface, body, timeout)

            def get(self, path, interface, timeout=0.0):
                self.timeouts.append(("GET", path, timeout))
                return super().get(path, interface, timeout)

        adapter = RecordingAdapter()
        adapter.send(SER, b"\x01")
        adapter.receive(ETH)
        self.assertEqual(adapter.timeouts, [("POST", "serials", 3.0), ("GET", "ethernet", 2.0)])
        adapter = RecordingAdapter(timeout=0.5)
        adapter.send(SER, b"\x01")
        self.assertEqual(adapter.timeouts, [("POST", "serials", 0.5)])

    def test_channel_with_an_unknown_protocol_is_an_error(self):
        class OtherChannel(Rs422Channel):
            protocol = "other"
        with self.assertRaises(ValueError):
            FakeUtsAdapter().send(OtherChannel(0), b"")


class EthernetThroughCommTests(CommTestCase):
    def test_tx_goes_to_post(self):
        self.send(bambaşka(0x07, SRC, 0x40, direction=Direction.TX))          # DIAG: Ethernet with header
        path, interface, body = self.adapter.posted[-1]
        self.assertEqual((path, interface), ("ethernet", 1))
        self.assertEqual(body["message"][:2], [0x55, 0xAA])                    # the header is on the line

    def test_rx_comes_from_get(self):
        rx = bambaşka(0x07, SRC, 0x40)
        rx.has_new()
        self.device_sends(bambaşka(0x07, SRC, 0x40, direction=Direction.TX, request=(5, 6, 7, 8)))
        self.expect_new(rx)
        self.assertEqual(list(rx.request), [5, 6, 7, 8])

    def test_rs422_goes_to_post(self):
        self.send(comut(SRC, DEST, 0x21, direction=Direction.TX))              # CONTROL: RS422
        path, interface, body = self.adapter.posted[-1]
        self.assertEqual((path, interface), ("serials", 0))
        self.assertTrue(comut(SRC, DEST, 0x21).validate(bytes(body["message"])))  # the packet, as a list of bytes

    def test_packet_rejected_by_the_envelope_is_unknown_on_its_channel(self):
        events = []
        self.comm.subscribe(UnknownReceived, events.append)
        self.comm.listen(MyChannels.DIAG)                                      # no RX message on DIAG here
        self.adapter.inject(MyChannels.DIAG, b"\x01\x02\x03")                    # no header
        deadline = time.monotonic() + self.timeout
        while not events and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual((events[0].channel, events[0].raw), (MyChannels.DIAG, b"\x01\x02\x03"))

    def test_rs422_rx_comes_from_get(self):
        rx = comut(DEST, SRC, 0x20)
        rx.has_new()
        self.device_sends(comut(DEST, SRC, 0x20, direction=Direction.TX, comut=(7, 8)))
        self.expect_new(rx)
        self.assertEqual(list(rx.comut), [7, 8])

    def test_post_without_an_answer_is_a_failed_send(self):
        errors = []
        self.comm.subscribe(LinkError, errors.append)

        def no_answer(path, interface, body, timeout):
            raise AdapterError(f"no answer within {timeout} s")

        self.adapter.post = no_answer
        msg = comut(SRC, DEST, 0x21, direction=Direction.TX)
        self.assertFalse(self.comm.send(msg))
        self.assertEqual(msg.peek_sent(), 0)
        deadline = time.monotonic() + self.timeout
        while not errors and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(str(errors[0].error), "no answer within 3.0 s")

    def test_failed_post_is_a_failed_send(self):
        errors = []
        self.comm.subscribe(LinkError, errors.append)

        def unreachable(*args):
            raise ConnectionError("UTS unreachable")

        self.adapter.post = unreachable
        msg = comut(SRC, DEST, 0x21, direction=Direction.TX)
        self.assertFalse(self.comm.send(msg))
        self.assertEqual(msg.peek_sent(), 0)                                   # not counted as sent
        deadline = time.monotonic() + self.timeout
        while not errors and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
