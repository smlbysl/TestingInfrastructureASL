"""Integration tests: Comm with the simulated UTS (FakeUtsClient), real threads."""
import time

from asl_testing import Direction, InvalidReceived, RxTimeout, Timing
from projects.example_project.messages import comut, motor_cmd
from tests.base import CommTestCase
from tests.settings import DEST, SRC


class CommTests(CommTestCase):
    def test_device_packet_is_received(self):
        status = comut(DEST, SRC, 0x20, rx=Timing(0.05))
        status.has_new()
        self.device_sends(comut(DEST, SRC, 0x20, direction=Direction.TX))
        self.assertEqual(self.comm.wait_new(status, timeout=0.5), 1)

    def test_bad_checksum_is_reported_as_invalid(self):
        invalid = []
        self.comm.subscribe(InvalidReceived, invalid.append)
        wire = comut(DEST, SRC, 0x20, direction=Direction.TX).pack()
        bad = bytearray(wire)
        bad[-1] ^= 0xFF
        ch = comut(DEST, SRC, 0x20).channel
        self.uts.inject(ch.protocol, ch.interface, bytes(bad))
        deadline = time.monotonic() + 0.5
        while not invalid and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(invalid), 1)

    def test_missing_periodic_message_times_out(self):
        status = comut(DEST, SRC, 0x20, rx=Timing(0.05, tolerance=2))
        timeouts = []
        self.comm.subscribe(RxTimeout, timeouts.append)
        deadline = time.monotonic() + 0.5
        while not timeouts and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(any(ev.message is status for ev in timeouts))

    def test_periodic_send_is_counted(self):
        motor = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.05))
        self.comm.start(motor)
        self.addCleanup(self.comm.stop, motor)
        self.assertGreaterEqual(self.comm.wait_sent(motor, timeout=0.5), 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
