"""Send locks: one lock per message (pack, request, after_send) and one POST at a time per interface."""

__author__ = "İsmail Baysal"

import threading
import time
import unittest

from asl_testing import Direction, FakeUtsClient, Timing
from projects.example_project.messages import motor_cmd, request, ser_cmd
from projects.example_project.types import Counter8
from tests.base import CommTestCase, open_comm
from tests.settings import DEST, SRC


class SlowUtsClient(FakeUtsClient):
    """Every POST takes `delay` seconds; counts how many POSTs run at the same time."""

    def __init__(self, delay: float = 0.0):
        super().__init__()
        self.delay = delay
        self.running = self.most = 0
        self._count = threading.Lock()

    def post(self, path, interface, body):
        with self._count:
            self.running += 1
            self.most = max(self.most, self.running)
        time.sleep(self.delay)
        with self._count:
            self.running -= 1
        super().post(path, interface, body)


class LockTests(CommTestCase):
    def use(self, uts: SlowUtsClient) -> None:
        self.comm.close()
        self.uts = uts
        self.comm = open_comm(uts)
        self.addCleanup(self.comm.close)

    def send_together(self, *messages) -> None:
        threads = [threading.Thread(target=self.comm.send, args=(m,)) for m in messages]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(self.timeout)

    def test_one_message_from_two_threads_never_repeats_its_counter(self):
        self.use(SlowUtsClient())
        counter_on_send = Counter8.on_send

        def slow_counter(field, msg):                        # widens the time between reading and writing the counter
            counter_on_send(field, msg)
            time.sleep(0.0005)

        Counter8.on_send = slow_counter
        self.addCleanup(setattr, Counter8, "on_send", counter_on_send)
        motor = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.001))
        self.comm.start(motor)
        self.addCleanup(self.comm.stop, motor)
        for _ in range(40):
            self.comm.send(motor)                            # the test thread, while the TX thread sends it too
        self.comm.stop(motor)
        counters = [motor_cmd.from_buffer_copy(bytes(body["message"])).messageCounter.val
                    for _, _, body in list(self.uts.posted)]
        self.assertGreater(len(counters), 40)
        self.assertEqual(len(counters), len(set(counters)))
        self.assertEqual(counters, sorted(counters))

    def test_posts_on_one_interface_do_not_overlap(self):
        self.use(SlowUtsClient(delay=0.05))
        self.send_together(motor_cmd(SRC, DEST, 0x30, direction=Direction.TX),       # both on CONTROL
                           request(SRC, DEST, 0x10, direction=Direction.TX))
        self.assertEqual((len(self.uts.posted), self.uts.most), (2, 1))

    def test_posts_on_different_interfaces_do_not_wait(self):
        self.use(SlowUtsClient(delay=0.05))
        started = time.monotonic()
        self.send_together(motor_cmd(SRC, DEST, 0x30, direction=Direction.TX),       # CONTROL
                           ser_cmd(SRC, DEST, 0x50, direction=Direction.TX))         # SER2
        self.assertEqual((len(self.uts.posted), self.uts.most), (2, 2))
        self.assertLess(time.monotonic() - started, 0.09)

    def test_hook_may_send_another_message(self):
        motor = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX)
        req = request(SRC, DEST, 0x10, direction=Direction.TX)
        motor.on_send(lambda m: self.comm.send(req))
        thread = threading.Thread(target=self.comm.send, args=(motor,))
        thread.start()
        thread.join(self.timeout)
        self.assertFalse(thread.is_alive())
        self.assertEqual((req.peek_sent(), motor.peek_sent()), (1, 1))


class ClientLockTests(unittest.TestCase):
    def test_lock_per_interface(self):
        uts = FakeUtsClient()
        self.assertIs(uts._post_lock("rs422", 0), uts._post_lock("rs422", 0))
        self.assertIsNot(uts._post_lock("rs422", 0), uts._post_lock("rs422", 2))
        self.assertIsNot(uts._post_lock("rs422", 1), uts._post_lock("ethernet", 1))


if __name__ == "__main__":
    unittest.main()
