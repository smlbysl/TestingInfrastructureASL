"""Answers of UTS: time of the send, buffer overflow, error answers."""

__author__ = "İsmail Baysal"

import time
import unittest

from asl_testing import (AdapterError, Direction, EthernetChannel, EthernetProtocol, LinkError, MessageSent,
                         RxOverflow, UtsAdapter)
from projects.example_project.channels import MyChannels
from projects.example_project.messages import comut
from tests.base import CommTestCase
from tests.settings import DEST, SRC

OK = {"status": "OK", "code": 200, "message": "OK"}


class ProtocolAnswerTests(unittest.TestCase):
    def test_post_answer(self):
        self.assertAlmostEqual(EthernetProtocol().sent_time({"statusInfo": OK, "timestamp": 1_500_000}), 1.5)
        self.assertIsNone(EthernetProtocol().sent_time({"statusInfo": OK}))
        self.assertIsNone(EthernetProtocol().sent_time(None))          # module that returns nothing

    def test_get_answer(self):
        answer = {"statusInfo": OK, "messages": [{"message": [1, 2], "timestamp": 7}], "isBufferOverflow": True}
        protocol = EthernetProtocol()
        self.assertEqual(protocol.items(answer), [{"message": [1, 2], "timestamp": 7}])
        self.assertTrue(protocol.overflow(answer))
        self.assertEqual((protocol.items({"statusInfo": OK}), protocol.overflow({})), ([], False))

    def test_simulate_gives_whole_microseconds(self):
        item = EthernetProtocol().simulate(EthernetChannel(1), b"\x01", 1.25)
        self.assertEqual(item["timestamp"], 1_250_000)


class ErrorAnswerTests(unittest.TestCase):
    def test_200_gives_the_body(self):
        self.assertEqual(UtsAdapter.answer(200, {"statusInfo": OK, "timestamp": 1}), {"statusInfo": OK, "timestamp": 1})

    def test_error_answer_is_an_adapter_error(self):
        body = {"statusInfo": {"status": "eINIT", "code": 503, "message": "HAL not initialised"}}
        with self.assertRaises(AdapterError) as caught:
            UtsAdapter.answer(503, body)
        self.assertEqual((caught.exception.status, caught.exception.code), (503, "eINIT"))
        self.assertIn("HAL not initialised", str(caught.exception))

    def test_error_answer_without_a_body(self):
        with self.assertRaises(AdapterError) as caught:
            UtsAdapter.answer(500, None)
        self.assertEqual(caught.exception.status, 500)


class ThroughCommTests(CommTestCase):
    def wait_for(self, events) -> None:
        deadline = time.monotonic() + self.timeout
        while not events and time.monotonic() < deadline:
            time.sleep(0.005)

    def test_message_sent_carries_the_uts_time(self):
        sent = []
        self.comm.subscribe(MessageSent, sent.append)
        before = time.time()
        self.assertTrue(self.comm.send(comut(SRC, DEST, 0x21, direction=Direction.TX)))
        self.wait_for(sent)
        self.assertAlmostEqual(sent[0].timestamp, before, delta=1.0)  # the fake answers with its clock

    def test_overflow_is_reported_and_packets_still_arrive(self):
        overflows = []
        self.comm.subscribe(RxOverflow, overflows.append)
        rx = comut(DEST, SRC, 0x20)
        rx.has_new()
        self.adapter.overflow(MyChannels.CONTROL)
        self.device_sends(comut(DEST, SRC, 0x20, direction=Direction.TX, comut=(1, 2)))
        self.expect_new(rx)
        self.wait_for(overflows)
        self.assertEqual([e.channel for e in overflows], [MyChannels.CONTROL])

    def test_error_answer_on_get_is_a_link_error(self):
        errors = []
        self.comm.subscribe(LinkError, errors.append)

        def not_ready(path, interface, timeout=0.0):
            return UtsAdapter.answer(503, {"statusInfo": {"status": "eINIT", "code": 503, "message": "not ready"}})

        self.adapter.get = not_ready
        comut(DEST, SRC, 0x20)
        self.wait_for(errors)
        self.assertEqual((errors[0].operation, errors[0].error.status), ("poll", 503))


if __name__ == "__main__":
    unittest.main()
