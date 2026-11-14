"""One RX and one TX thread per channel: a channel that hangs does not hold up the others."""

__author__ = "İsmail Baysal"

import threading
import time

from asl_testing import Direction, FakeBackend, RxTimeout, Timing
from projects.example_project.channels import MyChannels
from projects.example_project.messages import bambaşka, comut, motor_cmd, ser_cmd
from tests.base import CommTestCase, open_comm
from tests.settings import DEST, SRC

CONTROL, DIAG, SER2 = MyChannels.CONTROL, MyChannels.DIAG, MyChannels.SER2


class HangingBackend(FakeBackend):
    """Requests on the channels in `hanging` do not return until release() is called."""

    def __init__(self):
        super().__init__()
        self.hanging: set = set()
        self._released = threading.Event()

    def release(self) -> None:
        self._released.set()

    def send(self, channel, data):
        if channel in self.hanging:
            self._released.wait()
        return super().send(channel, data)

    def receive(self, channel):
        if channel in self.hanging:
            self._released.wait()
        return super().receive(channel)


class ChannelThreadTests(CommTestCase):
    def setUp(self):
        self.backend = HangingBackend()
        self.comm = open_comm(self.backend)
        self.addCleanup(self.comm.close)
        self.addCleanup(self.backend.release)                  # first, so close() can join the threads

    def threads(self, prefix: str) -> list[str]:
        return sorted(t.name for t in threading.enumerate() if t.name.startswith(prefix))

    def wait_until(self, condition, timeout: float = None) -> bool:
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while not condition() and time.monotonic() < deadline:
            time.sleep(0.005)
        return condition()

    # ---------------------------------------------------------------- RX

    def test_hanging_channel_does_not_delay_the_rx_of_another_channel(self):
        self.backend.hanging.add(CONTROL)
        comut(DEST, SRC, 0x20)                                               # CONTROL is polled, and hangs
        diag = bambaşka(0x07, SRC, 0x40)
        diag.has_new()
        time.sleep(0.05)                                                     # CONTROL is inside its request now
        started = time.monotonic()
        self.device_sends(bambaşka(0x07, SRC, 0x40, direction=Direction.TX, request=(1, 2, 3, 4)))
        self.expect_new(diag, timeout=0.3)
        self.assertLess(time.monotonic() - started, 0.3)

    def test_hanging_channel_causes_no_timeout_on_another_channel(self):
        timeouts = []
        self.comm.subscribe(RxTimeout, timeouts.append)
        self.backend.hanging.add(CONTROL)
        hanging = comut(DEST, SRC, 0x20, rx=Timing(0.05, tolerance=2))
        diag = bambaşka(0x07, SRC, 0x40, rx=Timing(0.05, tolerance=2))
        for _ in range(12):                                                  # the device keeps sending on DIAG
            self.device_sends(bambaşka(0x07, SRC, 0x40, direction=Direction.TX))
            time.sleep(0.025)
        time.sleep(0.05)
        late = [ev.message for ev in timeouts]
        self.assertTrue(any(m is hanging for m in late))                     # still checked while its channel hangs
        self.assertFalse(any(m is diag for m in late))

    def test_channel_gets_its_rx_thread_when_its_first_message_is_defined(self):
        self.assertEqual(self.threads("Rx-"), [])
        comut(DEST, SRC, 0x20)
        self.assertTrue(self.wait_until(lambda: self.threads("Rx-") == ["Rx-CONTROL"]))
        self.comm.listen(DIAG)
        self.assertTrue(self.wait_until(lambda: self.threads("Rx-") == ["Rx-CONTROL", "Rx-DIAG"]))

    def test_rx_thread_ends_when_the_channel_is_no_longer_needed(self):
        comut(DEST, SRC, 0x20)
        self.assertTrue(self.wait_until(lambda: self.threads("Rx-") == ["Rx-CONTROL"]))
        type(comut(DEST, SRC, 0x20)).clear_registry()
        self.assertTrue(self.wait_until(lambda: self.threads("Rx-") == []))

    # ---------------------------------------------------------------- TX

    def test_hanging_post_does_not_stop_the_periodic_send_of_another_channel(self):
        self.backend.hanging.add(CONTROL)
        self.start(motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.01)))      # CONTROL: hangs
        self.start(ser_cmd(SRC, DEST, 0x50, direction=Direction.TX, tx=Timing(0.01)))                          # SER2
        time.sleep(0.2)
        sent = [channel for channel, _ in self.backend.sent]
        self.assertGreaterEqual(sent.count(SER2), 10)
        self.assertEqual(sent.count(CONTROL), 0)

    def test_one_shot_send_does_not_wait_for_a_hanging_post_on_another_channel(self):
        self.backend.hanging.add(CONTROL)
        self.start(motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.01)))
        time.sleep(0.05)
        started = time.monotonic()
        self.send(bambaşka(0x07, SRC, 0x40, direction=Direction.TX))                         # DIAG
        self.assertLess(time.monotonic() - started, 0.1)

    def test_each_channel_with_periodic_messages_has_its_tx_thread(self):
        self.assertEqual(self.threads("Tx-"), [])
        self.start(motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.05)))
        self.start(comut(SRC, DEST, 0x21, direction=Direction.TX, tx=Timing(0.05)))           # CONTROL too
        self.start(ser_cmd(SRC, DEST, 0x50, direction=Direction.TX, tx=Timing(0.05)))
        self.assertEqual(self.threads("Tx-"), ["Tx-CONTROL", "Tx-SER2"])

    def test_messages_of_one_channel_keep_their_periods(self):
        fast = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.02))
        slow = comut(SRC, DEST, 0x21, direction=Direction.TX, tx=Timing(0.1))
        self.start(fast)
        self.start(slow)
        time.sleep(0.31)
        self.assertIn(fast.peek_sent(), range(14, 18))
        self.assertIn(slow.peek_sent(), range(3, 6))

    # ---------------------------------------------------------------- life cycle

    def test_close_ends_every_thread(self):
        comut(DEST, SRC, 0x20)
        self.start(motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.02)))
        self.assertTrue(self.wait_until(lambda: self.threads("Rx-") and self.threads("Tx-")))
        self.comm.close()
        self.assertEqual(self.threads("Rx") + self.threads("Tx-"), [])

    def test_periodic_message_started_before_open_is_sent_after_open(self):
        self.comm.close()
        comm = open_comm(self.backend)
        self.addCleanup(comm.close)
        comm.tx.stop_thread()                                                # as if not opened yet
        motor = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.02))
        comm.start(motor)
        time.sleep(0.05)
        self.assertEqual(motor.peek_sent(), 0)
        comm.tx.start_thread()
        self.assertTrue(self.wait_until(lambda: motor.peek_sent() > 0))


if __name__ == "__main__":
    import unittest
    unittest.main()
