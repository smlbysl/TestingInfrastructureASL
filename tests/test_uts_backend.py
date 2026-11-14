"""UTS backend: codecs of serial and Ethernet, paths, and the way through Comm (api.post / api.get)."""

__author__ = "İsmail Baysal"

import logging
import threading
import time
import unittest

from asl_testing import (Backend, Comm, Direction, EthernetChannel, FakeBackend, FakeUtsApi, FakeUtsBackend, LinkError,
                         Response, Rs422Channel, UnknownReceived, UtsBackend)
from asl_testing.backend.uts.codecs import EthernetCodec, SerialCodec
from projects.example_project.channels import MyChannels
from projects.example_project.messages import bambaşka, comut
from tests.base import CommTestCase, open_comm
from tests.settings import DEST, SRC

SER, ETH = Rs422Channel(0), EthernetChannel(1)


class SerialCodecTests(unittest.TestCase):
    def test_encode_decode(self):
        codec = SerialCodec(time_unit=1e-3)
        self.assertEqual(codec.encode(SER, b"\x01\x02"), {"message": [1, 2]})
        received = codec.decode(SER, codec.simulate(SER, b"\x01\x02", 1.5))
        self.assertEqual(received.data, b"\x01\x02")
        self.assertAlmostEqual(received.timestamp, 1.5)

    def test_path(self):
        self.assertEqual(SerialCodec.path, "serials")


class EthernetCodecTests(unittest.TestCase):
    def test_encode(self):
        self.assertEqual(EthernetCodec().encode(ETH, b"\x01\x02"), {"message": [1, 2]})

    def test_decode(self):
        received = EthernetCodec().decode(ETH, {"message": [1, 2], "timestamp": 5})
        self.assertEqual((received.data, received.timestamp), (b"\x01\x02", 5))

    def test_time_unit(self):
        received = EthernetCodec(time_unit=1e-6).decode(ETH, {"message": [], "timestamp": 2_000_000})
        self.assertAlmostEqual(received.timestamp, 2.0)

    def test_simulate_is_what_decode_reads(self):
        codec = EthernetCodec(time_unit=1e-3)
        received = codec.decode(ETH, codec.simulate(ETH, b"\xAA\xBB", 1.5))
        self.assertEqual(received.data, b"\xAA\xBB")
        self.assertAlmostEqual(received.timestamp, 1.5)


class UtsBackendTests(unittest.TestCase):
    def test_send_posts_the_body_on_the_path_of_the_bus(self):
        api = FakeUtsApi()
        self.assertTrue(UtsBackend(api).send(SER, b"\x01\x02"))
        self.assertEqual(api.posted, [("serials", 0, {"message": [1, 2]})])

    def test_receive_decodes_the_items(self):
        api = FakeUtsApi()
        api.put("ethernet", 1, {"message": [1, 2], "timestamp": 3})
        response = UtsBackend(api).receive(ETH)
        self.assertEqual([(r.data, r.timestamp) for r in response.data], [(b"\x01\x02", 3)])
        self.assertEqual(UtsBackend(api).receive(ETH).data, [])                # drained

    def test_failed_get_is_returned_as_it_is(self):
        api = FakeUtsApi()
        api.get = lambda path, interface, timeout: Response(ok=False, status=503, code="BUSY", message="busy")
        response = UtsBackend(api).receive(ETH)
        self.assertEqual((bool(response), response.status, response.code), (False, 503, "BUSY"))

    def test_bus_without_a_codec_is_an_error(self):
        class OtherChannel(Rs422Channel):
            bus = "other"
        with self.assertRaises(ValueError):
            UtsBackend(FakeUtsApi()).send(OtherChannel(0), b"")

    def test_exception_of_the_api_becomes_a_failed_response(self):
        api = FakeUtsApi()

        def unreachable(*args, **kwargs):
            raise ConnectionError("UTS unreachable")

        api.post = unreachable
        response = UtsBackend(api).send(SER, b"")
        self.assertEqual((bool(response), response.status, response.message),
                         (False, None, "ConnectionError: UTS unreachable"))

    def test_fake_backend_is_a_backend_without_control(self):
        self.assertIsInstance(FakeBackend(), Backend)
        self.assertIsNone(FakeBackend().control)


class RecordingApi(FakeUtsApi):
    """Keeps the timeout of every request; a POST takes `delay` seconds and counts how many run at once."""

    def __init__(self, delay: float = 0.0):
        super().__init__()
        self.timeouts: list[tuple[str, str, float]] = []
        self.delay = delay
        self.running = self.most = 0
        self._count = threading.Lock()

    def post(self, path, interface, body, timeout=0.0):
        self.timeouts.append(("POST", path, timeout))
        with self._count:
            self.running += 1
            self.most = max(self.most, self.running)
        time.sleep(self.delay)
        with self._count:
            self.running -= 1
        return super().post(path, interface, body, timeout)

    def get(self, path, interface, timeout=0.0):
        self.timeouts.append(("GET", path, timeout))
        return super().get(path, interface, timeout)


class TimeoutTests(unittest.TestCase):
    def test_every_request_gets_the_timeout_of_its_bus(self):
        api = RecordingApi()
        backend = UtsBackend(api)
        backend.send(SER, b"")
        backend.receive(SER)
        backend.send(ETH, b"")
        backend.receive(ETH)
        self.assertEqual(api.timeouts, [("POST", "serials", 3.0), ("GET", "serials", 3.0),
                                        ("POST", "ethernet", 2.0), ("GET", "ethernet", 2.0)])

    def test_timeout_given_to_the_backend_is_used_for_every_bus(self):
        api = RecordingApi()
        backend = UtsBackend(api, timeout=0.5)
        backend.send(SER, b"")
        backend.receive(ETH)
        self.assertEqual([t for _, _, t in api.timeouts], [0.5, 0.5])

    def test_duration_of_the_request_is_in_the_response(self):
        response = UtsBackend(RecordingApi(delay=0.02)).send(SER, b"")
        self.assertGreaterEqual(response.elapsed, 0.02)


class LogTests(unittest.TestCase):
    def test_failed_request_is_logged_as_an_error_with_its_details(self):
        api = FakeUtsApi()
        api.post = lambda *args, **kwargs: Response(ok=False, status=503, code="BUSY", message="tx queue full")
        with self.assertLogs("asl_testing.uts", logging.ERROR) as logs:
            UtsBackend(api).send(SER, b"")
        self.assertIn("POST /serials/0 failed: status 503, code BUSY, tx queue full", logs.output[0])

    def test_successful_post_is_logged_at_debug(self):
        with self.assertLogs("asl_testing.uts", logging.DEBUG) as logs:
            UtsBackend(FakeUtsApi()).send(ETH, b"\x01")
        self.assertEqual(logs.records[0].levelno, logging.DEBUG)
        self.assertIn("POST /ethernet/1 ok", logs.output[0])

    def test_get_is_logged_only_when_it_returned_items(self):
        api = FakeUtsApi()
        backend = UtsBackend(api)
        with self.assertNoLogs("asl_testing.uts", logging.DEBUG):
            backend.receive(ETH)
        api.put("ethernet", 1, {"message": [1]})
        with self.assertLogs("asl_testing.uts", logging.DEBUG) as logs:
            backend.receive(ETH)
        self.assertIn("GET /ethernet/1 ok", logs.output[0])
        self.assertIn("1 item(s)", logs.output[0])


class TxLockTests(unittest.TestCase):
    """UTS may overwrite a message whose POST is not answered yet: one POST at a time per interface."""

    def post_together(self, first, second) -> RecordingApi:
        api = RecordingApi(delay=0.05)
        backend = UtsBackend(api)
        threads = [threading.Thread(target=backend.send, args=(ch, b"\x01")) for ch in (first, second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(api.posted), 2)
        return api

    def test_two_posts_to_one_interface_do_not_overlap(self):
        self.assertEqual(self.post_together(SER, SER).most, 1)

    def test_posts_to_different_interfaces_do_not_wait_for_each_other(self):
        self.assertEqual(self.post_together(SER, ETH).most, 2)
        self.assertEqual(self.post_together(SER, Rs422Channel(1)).most, 2)

    def test_get_does_not_wait_for_a_post_on_the_same_interface(self):
        api = RecordingApi(delay=0.2)
        backend = UtsBackend(api)
        post = threading.Thread(target=backend.send, args=(SER, b"\x01"))
        post.start()
        time.sleep(0.02)
        started = time.monotonic()
        backend.receive(SER)
        self.assertLess(time.monotonic() - started, 0.1)
        post.join()


class UtsThroughCommTests(CommTestCase):
    """The example project on the UTS backend: what reaches UTS and what comes back."""

    def setUp(self):
        self.backend = FakeUtsBackend()
        self.comm = open_comm(self.backend)
        self.addCleanup(self.comm.close)

    def test_ethernet_tx_goes_to_post(self):
        self.send(bambaşka(0x07, SRC, 0x40, direction=Direction.TX))          # DIAG: Ethernet with header
        path, interface, body = self.backend.posted[-1]
        self.assertEqual((path, interface), ("ethernet", 1))
        self.assertEqual(body["message"][:2], [0x55, 0xAA])                    # the header is on the line

    def test_ethernet_rx_comes_from_get(self):
        rx = bambaşka(0x07, SRC, 0x40)
        rx.has_new()
        self.device_sends(bambaşka(0x07, SRC, 0x40, direction=Direction.TX, request=(5, 6, 7, 8)))
        self.expect_new(rx)
        self.assertEqual(list(rx.request), [5, 6, 7, 8])

    def test_serial_tx_goes_to_post(self):
        self.send(comut(SRC, DEST, 0x21, direction=Direction.TX))              # CONTROL: RS422
        path, interface, body = self.backend.posted[-1]
        self.assertEqual((path, interface), ("serials", 0))
        self.assertTrue(comut(SRC, DEST, 0x21).validate(bytes(body["message"])))  # the packet, as a list of bytes

    def test_serial_rx_comes_from_get(self):
        rx = comut(DEST, SRC, 0x20)
        rx.has_new()
        self.device_sends(comut(DEST, SRC, 0x20, direction=Direction.TX, comut=(7, 8)))
        self.expect_new(rx)
        self.assertEqual(list(rx.comut), [7, 8])

    def test_response_of_the_post_is_returned_by_send(self):
        response = self.comm.send(comut(SRC, DEST, 0x21, direction=Direction.TX))
        self.assertEqual((bool(response), response.status), (True, 200))

    def test_rejected_post_is_a_failed_send(self):
        errors = []
        self.comm.subscribe(LinkError, errors.append)
        self.backend.api.post = lambda *args, **kwargs: Response(ok=False, status=500, code="TX", message="not sent")
        msg = comut(SRC, DEST, 0x21, direction=Direction.TX)
        response = self.comm.send(msg)
        self.assertEqual((bool(response), response.status), (False, 500))
        self.assertEqual(msg.peek_sent(), 0)                                   # not counted as sent
        deadline = time.monotonic() + self.timeout
        while not errors and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(errors[0].error.response.code, "TX")

    def test_rejected_get_is_a_link_error_and_polling_goes_on(self):
        errors = []
        self.comm.subscribe(LinkError, errors.append)
        rx = comut(DEST, SRC, 0x20)
        rx.has_new()
        get = self.backend.api.get
        self.backend.api.get = lambda *args, **kwargs: Response(ok=False, status=503, message="busy")
        deadline = time.monotonic() + self.timeout
        while not errors and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(errors[0].operation, "poll")
        self.backend.api.get = get
        self.device_sends(comut(DEST, SRC, 0x20, direction=Direction.TX))
        self.expect_new(rx)

    def test_control_uses_the_path_of_the_bus(self):
        self.comm.control.set_config(MyChannels.CONTROL, baudRate=115200)
        self.assertEqual(self.backend.api.configs[("serials", 0)], {"baudRate": 115200})


class BackendThroughCommTests(CommTestCase):
    """Behaviour that does not depend on the backend (FakeBackend)."""

    def test_sent_bytes_are_the_bytes_on_the_line(self):
        self.send(bambaşka(0x07, SRC, 0x40, direction=Direction.TX))
        channel, data = self.backend.sent[-1]
        self.assertEqual((channel, data[:2]), (MyChannels.DIAG, b"\x55\xAA"))

    def test_packet_rejected_by_the_envelope_is_unknown_on_its_channel(self):
        events = []
        self.comm.subscribe(UnknownReceived, events.append)
        self.comm.listen(MyChannels.DIAG)                                      # no RX message on DIAG here
        self.backend.inject(MyChannels.DIAG, b"\x01\x02\x03")              # no header
        deadline = time.monotonic() + self.timeout
        while not events and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual((events[0].channel, events[0].raw), (MyChannels.DIAG, b"\x01\x02\x03"))

    def test_exception_in_the_backend_is_a_failed_send(self):
        errors = []
        self.comm.subscribe(LinkError, errors.append)

        def unreachable(*args):
            raise ConnectionError("UTS unreachable")

        self.backend.send = unreachable
        msg = comut(SRC, DEST, 0x21, direction=Direction.TX)
        self.assertFalse(self.comm.send(msg))
        self.assertEqual(msg.peek_sent(), 0)                                   # not counted as sent
        deadline = time.monotonic() + self.timeout
        while not errors and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(errors), 1)

    def test_comm_without_backend_control(self):
        self.assertIsNone(self.comm.control)


if __name__ == "__main__":
    unittest.main()
