"""Send locks: one lock per message (pack, request, after_send) and one POST at a time per interface."""

__author__ = "İsmail Baysal"

import threading
import time
import unittest

from asl_testing import Direction, FakeUtsAdapter, Timing
from projects.example_project.messages import motor_cmd, request, ser_cmd
from projects.example_project.types import Counter8
from tests.base import CommTestCase, open_comm
from tests.settings import DEST, SRC


class SlowUtsAdapter(FakeUtsAdapter):
    """Every POST takes `delay` seconds; counts how many POSTs run at the same time."""

    def __init__(self, delay: float = 0.0):
        super().__init__()
        self.delay = delay
        self.running = self.most = 0
        self._count = threading.Lock()

    def post(self, path, interface, body, timeout=0.0):
        with self._count:
            self.running += 1
            self.most = max(self.most, self.running)
        time.sleep(self.delay)
        with self._count:
            self.running -= 1
        super().post(path, interface, body, timeout)


class LockTests(CommTestCase):
    def use(self, adapter: SlowUtsAdapter) -> None:
        self.comm.close()
        self.adapter = adapter
        self.comm = open_comm(adapter)
        self.addCleanup(self.comm.close)

    def send_together(self, *messages) -> None:
        threads = [threading.Thread(target=self.comm.send, args=(m,)) for m in messages]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(self.timeout)

    def test_one_message_from_two_threads_never_repeats_its_counter(self):
        self.use(SlowUtsAdapter())
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
        deadline = time.monotonic() + self.timeout
        while len(self.adapter.posted) < 50 and time.monotonic() < deadline:
            time.sleep(0.001)                                # the TX thread sends some more on its own
        self.comm.stop(motor)
        counters = [motor_cmd.from_buffer_copy(bytes(body["message"])).messageCounter.val
                    for _, _, body in list(self.adapter.posted)]
        self.assertGreaterEqual(len(counters), 50)
        self.assertEqual(len(counters), len(set(counters)))
        self.assertEqual(counters, sorted(counters))

    def test_posts_on_one_interface_do_not_overlap(self):
        self.use(SlowUtsAdapter(delay=0.05))
        self.send_together(motor_cmd(SRC, DEST, 0x30, direction=Direction.TX),       # both on CONTROL
                           request(SRC, DEST, 0x10, direction=Direction.TX))
        self.assertEqual((len(self.adapter.posted), self.adapter.most), (2, 1))

    def test_posts_on_different_interfaces_do_not_wait(self):
        self.use(SlowUtsAdapter(delay=0.05))
        started = time.monotonic()
        self.send_together(motor_cmd(SRC, DEST, 0x30, direction=Direction.TX),       # CONTROL
                           ser_cmd(SRC, DEST, 0x50, direction=Direction.TX))         # SER2
        self.assertEqual((len(self.adapter.posted), self.adapter.most), (2, 2))
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


class HoldingUtsAdapter(FakeUtsAdapter):
    """post() can be held: entered is set when a POST arrives, it waits until release() is called."""

    def __init__(self):
        super().__init__()
        self.holding = False
        self.entered = threading.Event()
        self._released = threading.Event()

    def release(self) -> None:
        self.holding = False
        self._released.set()

    def post(self, path, interface, body, timeout=0.0):
        if self.holding:
            self.entered.set()
            self._released.wait()
        super().post(path, interface, body, timeout)


class LockedUpdateTests(CommTestCase):
    def setUp(self):
        self.adapter = HoldingUtsAdapter()
        self.comm = open_comm(self.adapter)
        self.addCleanup(self.comm.close)
        self.addCleanup(self.adapter.release)
        self.addCleanup(self.comm.stop_all)

    def sent(self) -> list[motor_cmd]:
        return [motor_cmd.from_buffer_copy(bytes(body["message"])) for _, _, body in list(self.adapter.posted)]

    def wait_until(self, condition) -> bool:
        deadline = time.monotonic() + self.timeout
        while not condition() and time.monotonic() < deadline:
            time.sleep(0.002)
        return bool(condition())

    def test_fields_written_in_the_block_go_out_together(self):
        motor = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.002))
        self.comm.start(motor)
        for i in range(1, 6):
            with motor.locked_update():
                motor.speed = i * 100
                time.sleep(0.01)                             # several periods pass in the middle of the block
                motor.cmd.mode = i
            time.sleep(0.005)                                # the TX thread gets the lock between the blocks
        self.assertTrue(self.wait_until(lambda: (500, 5) in [(p.speed, p.cmd.mode) for p in self.sent()]))
        self.comm.stop(motor)
        packets = [(p.speed, p.cmd.mode) for p in self.sent()]
        self.assertIn((500, 5), packets)
        self.assertEqual([p for p in packets if p != (0, 1) and p[0] != p[1] * 100], [])

    def test_request_bit_written_during_a_send_is_not_lost(self):      # B12
        motor = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, tx=Timing(0.01))
        self.adapter.holding = True
        self.comm.start(motor)
        self.assertTrue(self.adapter.entered.wait(self.timeout))           # the TX thread is inside the POST

        def request():
            with motor.locked_update():
                motor.cmd.startReq = 1

        writer = threading.Thread(target=request)
        writer.start()
        time.sleep(0.02)
        self.assertTrue(writer.is_alive())                             # waits for the send and its after_send
        self.adapter.release()
        writer.join(self.timeout)
        self.assertTrue(self.wait_until(lambda: any(p.cmd.startReq for p in self.sent())))
        self.assertTrue(self.wait_until(lambda: motor.cmd.startReq == 0))   # cleared after it went out

    def test_send_inside_the_block(self):
        motor = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX)
        with motor.locked_update():
            motor.speed = 42
            self.assertTrue(self.comm.send(motor))
        self.assertEqual(self.sent()[-1].speed, 42)


class AdapterLockTests(unittest.TestCase):
    def test_lock_per_interface(self):
        adapter = FakeUtsAdapter()
        self.assertIs(adapter._post_lock("serials", 0), adapter._post_lock("serials", 0))
        self.assertIsNot(adapter._post_lock("serials", 0), adapter._post_lock("serials", 2))
        self.assertIsNot(adapter._post_lock("serials", 1), adapter._post_lock("ethernet", 1))


if __name__ == "__main__":
    unittest.main()
