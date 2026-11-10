"""Message history (ring buffer), snapshot and consistent pack (docs/RX_HISTORY_HANDOFF.md, test plan)."""
import sys
import threading
import time
import unittest
from ctypes import BigEndianStructure, c_uint8, c_uint16

import asl_testing
from asl_testing import (BaseMessageStructure, ChannelSet, Direction, EthernetChannel, MessageReceived,
                         MessageSent, Timing)
from projects.example_project.messages import comut, motor_cmd, ser_report
from projects.example_project.types import CRC16
from tests.base import CommTestCase
from tests.settings import DEST, SRC


def wait_until(condition, timeout=1.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.005)
    return condition()


class RxHistoryTests(CommTestCase):
    def _send_values(self, values):
        device = comut(DEST, SRC, 0x20, direction=Direction.TX)
        for v in values:
            device.comut[0] = v
            self.uts.device_sends(device)

    def test_every_packet_of_one_poll_is_kept_in_order(self):
        status = comut(DEST, SRC, 0x20)
        mark = status.rx_history.mark()
        self._send_values([1, 2, 3, 4, 5])                  # all in the buffer before the next poll
        self.assertTrue(wait_until(lambda: len(status.rx_history.since(mark)) == 5))
        records = status.rx_history.since(mark)
        self.assertEqual([r.snapshot().comut[0] for r in records], [1, 2, 3, 4, 5])
        self.assertEqual([r.seq for r in records], sorted(r.seq for r in records))
        self.assertEqual(status.comut[0], 5)                # the live object shows the last one

    def test_wait_for_finds_a_value_in_the_middle_of_a_batch(self):
        status = comut(DEST, SRC, 0x20)
        mark = status.rx_history.mark()
        self._send_values([7, 10, 7])
        rec = self.comm.wait_for(status, lambda s: s.comut[0] == 10, timeout=1.0, after=mark)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.snapshot().comut[0], 10)

    def test_wait_for_times_out(self):
        status = comut(DEST, SRC, 0x20)
        t0 = time.monotonic()
        self.assertIsNone(self.comm.wait_for(status, lambda s: s.comut[0] == 99, timeout=0.2))
        self.assertGreaterEqual(time.monotonic() - t0, 0.19)

    def test_overflow_drops_the_oldest(self):
        status = comut(DEST, SRC, 0x20, history=3)
        self._send_values([1, 2, 3, 4, 5])
        self.assertTrue(wait_until(lambda: status.rx_history.dropped == 2))
        self.assertEqual([r.snapshot().comut[0] for r in status.rx_history.since()], [3, 4, 5])

    def test_two_readers_do_not_consume_each_other(self):
        status = comut(DEST, SRC, 0x20)
        first, second = status.rx_history.mark(), status.rx_history.mark()
        self._send_values([1, 2])
        self.assertTrue(wait_until(lambda: len(status.rx_history.since(first)) == 2))
        self.assertEqual(len(status.rx_history.since(second)), 2)

    def test_created_again_starts_with_an_empty_history(self):
        status = comut(DEST, SRC, 0x20)
        self._send_values([1])
        self.assertTrue(wait_until(lambda: len(status.rx_history) == 1))
        again = comut(DEST, SRC, 0x20)
        self.assertEqual(len(again.rx_history), 0)

    def test_event_image_is_the_packet_before_callouts(self):
        status = comut(DEST, SRC, 0x20)
        status.on_receive(lambda m: m.comut.__setitem__(1, 0xEEEE))    # a callout changes the live object
        events = []
        self.comm.on_receive(status, events.append)
        self._send_values([42])
        self.assertTrue(wait_until(lambda: events))
        snap = events[0].snapshot()
        self.assertEqual((snap.comut[0], snap.comut[1]), (42, 0))
        self.assertEqual(events[0].image, status.rx_history.last().image)


class TxConsistencyTests(CommTestCase):
    def test_every_sent_packet_matches_its_checksum(self):
        """B9: the test thread writes fields while the scheduler sends; no packet with an old CRC.

        The thread switch interval is made tiny so the writer often runs inside pack().
        """
        interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        self.addCleanup(sys.setswitchinterval, interval)
        motor = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.002))
        sent = []
        self.comm.subscribe(MessageSent, sent.append, where=motor)
        self.start(motor)
        end = time.monotonic() + 0.4
        v = 0
        while time.monotonic() < end:
            v = (v + 1) % 30000
            motor.speed = v
        self.comm.stop(motor)
        self.assertTrue(wait_until(lambda: len(sent) == motor.tx_state.count))
        body = motor_cmd.checksum.offset
        bad = []
        for _, _, item in self.uts.sent:
            data = bytes(item["message"])
            if CRC16().compute(data[:body]) != int.from_bytes(data[body:body + 2], "little"):
                bad.append(data.hex())
        self.assertGreater(len(self.uts.sent), 20)
        self.assertEqual(bad, [])
        for ev in sent:                                     # B11: the image is the packet that was sent
            self.assertEqual(ev.raw, ev.image)
        self.assertEqual(len(motor.tx_history), min(motor.tx_state.count, motor.tx_history.capacity))

    def test_pack_writes_counter_back(self):
        motor = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX)
        first = motor.messageCounter.val
        self.send(motor)
        self.assertEqual(motor.messageCounter.val, (first + 1) % 256)
        self.assertEqual(motor.tx_history.last().snapshot().messageCounter.val, motor.messageCounter.val)


class LayoutTests(unittest.TestCase):
    def test_big_endian_bitfields_decode_and_snapshot(self):
        class Ch(ChannelSet):
            ETH = EthernetChannel(7)

        class BeProj(BaseMessageStructure, BigEndianStructure):
            _fields_ = [("word", c_uint16), ("a", c_uint8, 3), ("b", c_uint8, 5)]
            _channel = Ch.ETH

        tx = BeProj(direction=Direction.TX, word=0x1234, a=5, b=17)
        rx = BeProj()
        self.assertTrue(rx.decode(tx.pack()))
        snap = rx.snapshot()
        self.assertEqual((rx.word, rx.a, rx.b), (0x1234, 5, 17))
        self.assertEqual((snap.word, snap.a, snap.b), (0x1234, 5, 17))
        BeProj.clear_registry()

    def test_variable_size_unused_part_is_zero(self):
        rx = ser_report(DEST, SRC, 0)
        tx = ser_report(DEST, SRC, 0, direction=Direction.TX)
        tx.count = 8
        for i in range(8):
            tx.values[i] = 100 + i
        self.assertTrue(rx.decode(tx.pack()))
        tx.count = 2
        packet = tx.pack()
        self.assertTrue(rx.decode(packet))
        self.assertEqual(list(rx.values), [100, 101, 0, 0, 0, 0, 0, 0])
        self.assertEqual(rx.checksum.val, int.from_bytes(packet[-2:], "little"))   # trailer at the checksum field
        self.assertEqual(rx.checksum.val, tx.checksum.val)


class GilCheckTests(unittest.TestCase):
    def test_free_threaded_build_is_refused(self):
        original = getattr(sys, "_is_gil_enabled", None)
        sys._is_gil_enabled = lambda: False
        try:
            with self.assertRaises(RuntimeError):
                asl_testing._check_gil()
        finally:
            if original is None:
                del sys._is_gil_enabled
            else:
                sys._is_gil_enabled = original


if __name__ == "__main__":
    unittest.main()
