"""Thread safety of the message object while the RX thread writes into it."""
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


if __name__ == "__main__":
    unittest.main()
