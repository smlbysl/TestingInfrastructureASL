"""Received packets kept in order (rx_history), snapshot, and the wait on a condition."""
import logging
import threading
import time
import unittest

from asl_testing import Direction, MessageReceived
from projects.example_project.messages import diag_log, motor_cmd
from tests.base import CommTestCase
from tests.settings import DEST, SRC


def packet(speed: int) -> bytes:
    tx = motor_cmd(DEST, SRC, 0x30, direction=Direction.TX)
    tx.speed = speed
    return tx.pack()


class HistoryUnitTests(unittest.TestCase):
    def test_every_packet_is_kept_in_order(self):
        status = motor_cmd(DEST, SRC, 0x30)
        mark = status.rx_history.mark()
        for speed in (0, 10, 20, 30):                         # as if they came in one UTS poll
            self.assertTrue(status.decode(packet(speed), timestamp=speed / 1000))
        self.assertEqual(status.speed, 30)                    # the live object: the last packet
        records = status.rx_history.since(mark)
        self.assertEqual([r.snapshot().speed for r in records], [0, 10, 20, 30])
        self.assertEqual([r.timestamp for r in records], [0, 0.01, 0.02, 0.03])
        self.assertEqual(sorted(r.seq for r in records), [r.seq for r in records])

    def test_invalid_packet_is_not_kept(self):
        status = motor_cmd(DEST, SRC, 0x30)
        bad = bytearray(packet(5))
        bad[-1] ^= 0xFF
        self.assertFalse(status.decode(bytes(bad)))
        self.assertEqual(len(status.rx_history), 0)

    def test_mark_skips_older_packets(self):
        status = motor_cmd(DEST, SRC, 0x30)
        status.decode(packet(1))
        mark = status.rx_history.mark()
        status.decode(packet(2))
        self.assertEqual([r.snapshot().speed for r in status.rx_history.since(mark)], [2])

    def test_two_readers_do_not_affect_each_other(self):
        status = motor_cmd(DEST, SRC, 0x30)
        first = status.rx_history.mark()
        status.decode(packet(1))
        second = status.rx_history.mark()
        status.decode(packet(2))
        self.assertEqual(len(status.rx_history.since(first)), 2)
        self.assertEqual(len(status.rx_history.since(second)), 1)
        self.assertEqual(len(status.rx_history.since(first)), 2)     # reading removed nothing

    def test_overflow_drops_the_oldest_and_counts(self):
        status = motor_cmd(DEST, SRC, 0x30, history=3)
        with self.assertLogs("asl_testing.message.history", logging.WARNING) as logs:
            for speed in range(5):
                status.decode(packet(speed))
        self.assertEqual([r.snapshot().speed for r in status.rx_history.since(0)], [2, 3, 4])
        self.assertEqual(status.rx_history.dropped, 2)
        self.assertEqual(len(logs.records), 1)                      # warned once, not per packet

    def test_capacity_from_the_class(self):
        class short_status(motor_cmd):
            _history = 2
        self.assertEqual(short_status(DEST, SRC, 0x31).rx_history.capacity, 2)
        self.assertEqual(motor_cmd(DEST, SRC, 0x30).rx_history.capacity, 64)

    def test_new_object_starts_empty(self):
        status = motor_cmd(DEST, SRC, 0x30)
        status.decode(packet(1))
        self.assertEqual(len(motor_cmd(DEST, SRC, 0x30).rx_history), 0)

    def test_tx_only_message_has_no_history(self):
        self.assertIsNone(motor_cmd(SRC, DEST, 0x30, direction=Direction.TX).rx_history)

    def test_variable_size_record(self):
        rx = diag_log(DEST, SRC, 0x40)
        tx = diag_log(DEST, SRC, 0x40, direction=Direction.TX)
        tx.count = 2
        tx.entries[0], tx.entries[1] = 11, 22
        self.assertTrue(rx.decode(tx.pack()))
        snap = rx.rx_history.last().snapshot()
        self.assertEqual((snap.count, snap.entries[0], snap.entries[1], snap.entries[2]), (2, 11, 22, 0))

    def test_snapshot_is_a_separate_copy(self):
        status = motor_cmd(DEST, SRC, 0x30)
        status.decode(packet(7))
        snap = status.snapshot()
        status.decode(packet(8))
        self.assertEqual((snap.speed, status.speed), (7, 8))


class WaitForUnitTests(unittest.TestCase):
    def test_finds_a_record_already_there(self):
        status = motor_cmd(DEST, SRC, 0x30)
        for speed in (0, 10, 20):
            status.decode(packet(speed))
        found = status.rx_history.wait_for(lambda s: s.speed == 10, after=0, timeout=0)
        self.assertEqual(found.snapshot().speed, 10)

    def test_wakes_up_when_the_record_arrives(self):
        status = motor_cmd(DEST, SRC, 0x30)
        mark = status.rx_history.mark()
        threading.Timer(0.05, lambda: [status.decode(packet(s)) for s in (5, 10, 15)]).start()
        started = time.monotonic()
        found = status.rx_history.wait_for(lambda s: s.speed == 10, after=mark, timeout=2.0)
        self.assertEqual(found.snapshot().speed, 10)
        self.assertLess(time.monotonic() - started, 1.0)

    def test_timeout_returns_none(self):
        status = motor_cmd(DEST, SRC, 0x30)
        status.decode(packet(1))
        self.assertIsNone(status.rx_history.wait_for(lambda s: s.speed == 99, after=0, timeout=0.05))


class HistoryThroughCommTests(CommTestCase):
    def test_packets_from_the_device_are_kept_in_order(self):
        status = motor_cmd(DEST, SRC, 0x30)
        mark = status.rx_history.mark()
        for speed in (0, 10, 20, 30):
            tx = motor_cmd(DEST, SRC, 0x30, direction=Direction.TX)
            tx.speed = speed
            self.device_sends(tx)
        deadline = time.monotonic() + self.timeout
        while len(status.rx_history.since(mark)) < 4 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual([r.snapshot().speed for r in status.rx_history.since(mark)], [0, 10, 20, 30])

    def test_event_carries_the_packet_of_the_record(self):
        status = motor_cmd(DEST, SRC, 0x30)
        status.on_receive(lambda m: setattr(m, "speed", -1))           # a callout changes the live object
        events = []
        self.comm.subscribe(MessageReceived, events.append)
        tx = motor_cmd(DEST, SRC, 0x30, direction=Direction.TX)
        tx.speed = 42
        self.device_sends(tx)
        deadline = time.monotonic() + self.timeout
        while not events and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(events[0].snapshot().speed, 42)                # the packet, not the changed object
        self.assertEqual(events[0].image, status.rx_history.last().image)
        self.assertEqual(status.speed, -1)


if __name__ == "__main__":
    unittest.main()
