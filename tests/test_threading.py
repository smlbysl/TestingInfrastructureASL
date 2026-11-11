"""Thread safety of the message object while the RX thread writes into it."""

__author__ = "İsmail Baysal"

import sys
import threading
import time
import unittest

from asl_testing import Direction
from projects.example_project.messages import diag_log, motor_cmd
from tests.settings import DEST, SRC


class DecodeIsAtomicTests(unittest.TestCase):
    """B1: a reader sees the previous or the new packet, never a cleared or half-written object."""

    def setUp(self):
        self._interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)               # switch threads as often as possible to expose races

    def tearDown(self):
        sys.setswitchinterval(self._interval)

    @staticmethod
    def _packet(cls, **values) -> bytes:
        tx = cls(DEST, SRC, 0x30 if cls is motor_cmd else 0x40, direction=Direction.TX)
        for name, value in values.items():
            setattr(tx, name, value)
        return tx.pack()

    def _race(self, msg, packets, read, allowed, duration=0.3) -> int:
        stop, bad = threading.Event(), []
        for raw in packets:
            self.assertTrue(msg.decode(raw))      # valid packets; the object starts with the last one

        def writer():
            while not stop.is_set():
                for raw in packets:
                    msg.decode(raw)

        thread = threading.Thread(target=writer, daemon=True)
        thread.start()
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            value = read(msg)
            if value not in allowed:
                bad.append(value)
        stop.set()
        thread.join()
        return len(bad)

    def test_single_field(self):
        msg = motor_cmd(DEST, SRC, 0x30)
        packets = [self._packet(motor_cmd, speed=100), self._packet(motor_cmd, speed=-100)]
        self.assertEqual(self._race(msg, packets, lambda m: m.speed, {100, -100}), 0)

    def test_variable_size_body(self):
        msg = diag_log(DEST, SRC, 0x40)
        packets = [self._packet(diag_log, count=1, entries=(7,) * 16),
                   self._packet(diag_log, count=3, entries=(9,) * 16)]
        self.assertEqual(self._race(msg, packets, lambda m: m.count, {1, 3}), 0)


class PackIsConsistentTests(unittest.TestCase):
    """B9, B10: while another thread writes fields, every packed packet is valid on the RX side."""

    def setUp(self):
        self._interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)

    def tearDown(self):
        sys.setswitchinterval(self._interval)

    @staticmethod
    def _race(msg, write, check, duration=0.3) -> int:
        stop = threading.Event()

        def writer():
            i = 0
            while not stop.is_set():
                write(msg, i)
                i += 1

        thread = threading.Thread(target=writer, daemon=True)
        thread.start()
        bad = 0
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            if not check(msg.pack()):
                bad += 1
        stop.set()
        thread.join()
        return bad

    def test_fixed_size_checksum_matches_the_values(self):                      # B9
        tx = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX)
        rx = motor_cmd(SRC, DEST, 0x30)
        self.assertEqual(self._race(tx, lambda m, i: setattr(m, "speed", i % 1000), rx.validate), 0)

    def test_variable_size_length_checksum_and_body_match(self):               # B10
        tx = diag_log(SRC, DEST, 0x40, direction=Direction.TX)
        rx = diag_log(SRC, DEST, 0x40)
        self.assertEqual(self._race(tx, lambda m, i: setattr(m, "count", 1 + i % 5), rx.validate), 0)


class PackKeepsValuesTests(unittest.TestCase):
    def test_hook_results_are_written_back(self):
        msg = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX)
        first = msg.messageCounter.val
        raw = msg.pack()
        self.assertEqual(msg.messageCounter.val, (first + 1) % 256)             # counter goes on from here
        self.assertEqual(bytes(msg)[-2:], raw[-2:])                             # checksum on the object too

    def test_value_written_during_pack_is_not_reverted(self):
        msg = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX)

        def write_meanwhile(m):                                                 # runs after the copy is taken
            m.speed = 77

        original = msg.cmd.__class__.on_send
        try:
            type(msg.cmd).on_send = lambda field, m: (original(field, m), write_meanwhile(msg))[0]
            msg.pack()
        finally:
            type(msg.cmd).on_send = original
        self.assertEqual(msg.speed, 77)                                         # not overwritten by the copy

    def test_wire_and_image_come_from_the_same_copy(self):                     # B11
        msg = diag_log(SRC, DEST, 0x40, direction=Direction.TX)
        msg.count = 2
        wire, image = msg._pack()
        body = msg.body_size()
        self.assertEqual(wire, image[:body] + image[msg._trailer_offset():])


if __name__ == "__main__":
    unittest.main()
