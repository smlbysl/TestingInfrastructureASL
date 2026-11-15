"""One TX thread per channel: a channel whose POST hangs does not hold up the periodic send of the others."""

__author__ = "İsmail Baysal"

import threading
import time

from asl_testing import Direction, FakeUtsAdapter, Timing
from projects.example_project.channels import MyChannels
from projects.example_project.messages import bambaşka, comut, motor_cmd, request, ser_cmd
from tests.base import CommTestCase, open_comm
from tests.settings import DEST, SRC

CONTROL, SER2 = MyChannels.CONTROL, MyChannels.SER2


class HangingUtsAdapter(FakeUtsAdapter):
    """POST on the channels in `hanging` does not return until release() is called."""

    def __init__(self):
        super().__init__()
        self.hanging: set = set()
        self._released = threading.Event()

    def release(self) -> None:
        self._released.set()

    def post(self, path, interface, body, timeout=0.0):
        if (path, interface) in {(self.protocol(ch).path, ch.interface) for ch in self.hanging}:
            self._released.wait()
        super().post(path, interface, body, timeout)

    def sent_on(self, channel) -> int:
        key = (self.protocol(channel).path, channel.interface)
        return sum(1 for path, interface, _ in list(self.posted) if (path, interface) == key)


class TxThreadTests(CommTestCase):
    def setUp(self):
        self.adapter = HangingUtsAdapter()
        self.comm = open_comm(self.adapter)
        self.addCleanup(self.comm.close)
        self.addCleanup(self.adapter.release)                  # runs first, so close() can join the threads
        self.addCleanup(self.comm.stop_all)

    def tx_threads(self) -> list[str]:
        return sorted(t.name for t in threading.enumerate() if t.name.startswith("Tx-"))

    def wait_until(self, condition) -> bool:
        deadline = time.monotonic() + self.timeout
        while not condition() and time.monotonic() < deadline:
            time.sleep(0.005)
        return bool(condition())

    def test_hanging_post_does_not_stop_another_channel(self):
        self.adapter.hanging.add(CONTROL)
        self.comm.start(motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.01)))   # CONTROL: hangs
        self.comm.start(ser_cmd(SRC, DEST, 0x50, direction=Direction.TX, tx=Timing(0.01)))     # SER2
        time.sleep(0.2)
        self.assertGreaterEqual(self.adapter.sent_on(SER2), 10)
        self.assertEqual(self.adapter.sent_on(CONTROL), 0)

    def test_one_shot_send_does_not_wait_for_a_hanging_channel(self):
        self.adapter.hanging.add(CONTROL)
        self.comm.start(motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.01)))
        time.sleep(0.05)
        started = time.monotonic()
        self.assertTrue(self.comm.send(bambaşka(0x07, SRC, 0x40, direction=Direction.TX)))      # DIAG
        self.assertLess(time.monotonic() - started, 0.1)

    def test_each_channel_with_periodic_messages_has_one_thread(self):
        self.assertEqual(self.tx_threads(), [])
        self.comm.start(motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.05)))
        self.comm.start(request(SRC, DEST, 0x10, direction=Direction.TX, tx=Timing(0.05)))     # CONTROL too
        self.comm.start(ser_cmd(SRC, DEST, 0x50, direction=Direction.TX, tx=Timing(0.05)))
        self.assertEqual(self.tx_threads(), ["Tx-CONTROL", "Tx-SER2"])

    def test_starting_on_one_channel_from_many_threads_opens_one_thread(self):
        messages = [comut(SRC, DEST, 0x21 + i, direction=Direction.TX, tx=Timing(0.05)) for i in range(8)]
        threads = [threading.Thread(target=self.comm.start, args=(m,)) for m in messages]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(self.timeout)
        self.assertEqual(self.tx_threads(), ["Tx-CONTROL"])
        self.assertEqual(len(self.comm.tx.running(CONTROL)), 8)
        self.assertTrue(self.wait_until(lambda: all(m.peek_sent() for m in messages)))

    def test_messages_of_one_channel_keep_their_periods(self):
        fast = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.02))
        slow = request(SRC, DEST, 0x10, direction=Direction.TX, tx=Timing(0.1))
        self.comm.start(fast)
        self.comm.start(slow)
        time.sleep(0.31)
        self.assertIn(fast.peek_sent(), range(14, 18))
        self.assertIn(slow.peek_sent(), range(3, 6))

    def test_close_ends_every_tx_thread(self):
        self.comm.start(motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.02)))
        self.comm.start(ser_cmd(SRC, DEST, 0x50, direction=Direction.TX, tx=Timing(0.02)))
        self.assertEqual(len(self.tx_threads()), 2)
        self.comm.close()
        self.assertEqual(self.tx_threads(), [])

    def test_message_started_before_open_is_sent_after_open(self):
        self.comm.close()
        comm = open_comm(self.adapter)
        self.addCleanup(comm.close)
        comm.tx.stop_thread()                               # as if not opened yet
        motor = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.02))
        comm.start(motor)
        time.sleep(0.05)
        self.assertEqual((motor.peek_sent(), self.tx_threads()), (0, []))
        comm.tx.start_thread()
        self.assertTrue(self.wait_until(lambda: motor.peek_sent() > 0))


if __name__ == "__main__":
    import unittest
    unittest.main()
