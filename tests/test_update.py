"""msg.update(): fields written together, safe against the periodic send (design 1, B12)."""

__author__ = "İsmail Baysal"

import ctypes
import threading
import time
import unittest
from ctypes import c_uint16

from asl_testing import Direction, FakeBackend, Timing
from projects.example_project.header import Family1
from projects.example_project.messages import comut, motor_cmd
from tests.base import CommTestCase, open_comm
from tests.settings import DEST, SRC


def tx_motor(**kw) -> motor_cmd:
    return motor_cmd(SRC, DEST, 0x30, direction=Direction.TX, **kw)


class UpdateTests(unittest.TestCase):
    def test_writes_the_fields(self):
        msg = tx_motor()
        msg.update(speed=500)
        msg.update({"cmd.mode": 3, "cmd.startReq": 1})
        self.assertEqual((msg.speed, msg.cmd.mode, msg.cmd.startReq), (500, 3, 1))

    def test_dict_and_keywords_together(self):
        msg = tx_motor()
        msg.update({"cmd.mode": 5}, speed=7)
        self.assertEqual((msg.speed, msg.cmd.mode), (7, 5))

    def test_field_type_gets_val(self):
        msg = tx_motor()
        msg.update(messageCounter=7)
        self.assertEqual(msg.messageCounter.val, 7)

    def test_array_field(self):
        msg = comut(SRC, DEST, 0x21, direction=Direction.TX)
        msg.update(comut=(5, 6))
        self.assertEqual(list(msg.comut), [5, 6])

    def test_wrong_name_raises_and_writes_nothing(self):
        msg = tx_motor()
        for wrong in ({"speed": 9, "sped": 1}, {"speed": 9, "cmd.mod": 1}, {"speed": 9, "speed.x": 1}):
            with self.subTest(values=wrong), self.assertRaises(AttributeError):
                msg.update(wrong)
            self.assertEqual(msg.speed, 0)
        self.assertNotIn("sped", msg.__dict__)

    def test_block_form(self):
        msg = tx_motor()
        with msg.update():
            msg.speed = 11
            msg.cmd.mode = 4
        self.assertEqual((msg.speed, msg.cmd.mode), (11, 4))

    def test_field_named_update_is_refused(self):
        with self.assertRaises(TypeError):
            class bad(Family1):
                _fields_ = [("update", c_uint16)]

    def test_update_inside_on_send_does_not_block(self):
        msg = tx_motor()
        msg.on_send(lambda m: m.update(speed=9))
        msg.pack()
        self.assertEqual(msg.speed, 9)

    def test_snapshot_of_a_snapshot_and_update_on_a_copy(self):
        snap = tx_motor().snapshot()
        snap.update(speed=3)                                   # a copy has no lock and is not shared
        with snap.update():
            snap.cmd.mode = 2
        self.assertEqual((snap.snapshot().speed, snap.cmd.mode), (3, 2))


class HoldingBackend(FakeBackend):
    """send() can be held: entered is set when a send arrives, the send waits until release() is called."""

    def __init__(self):
        super().__init__()
        self.holding = False
        self.entered = threading.Event()
        self._release = threading.Event()

    def release(self) -> None:
        self.holding = False
        self._release.set()

    def send(self, channel, data):
        if self.holding:
            self.entered.set()
            self._release.wait()
        return super().send(channel, data)


class PeriodicUpdateTests(CommTestCase):
    def setUp(self):
        self.backend = HoldingBackend()
        self.comm = open_comm(self.backend)
        self.addCleanup(self.comm.close)
        self.addCleanup(self.backend.release)

    def sent_motors(self) -> list[motor_cmd]:
        size = ctypes.sizeof(motor_cmd)                     # a new motor_cmd object would replace the started one
        return [motor_cmd.from_buffer_copy(data) for _, data in list(self.backend.sent)
                if len(data) == size and data[8:12] == (0x30).to_bytes(4, "little")]

    def wait_until(self, condition, timeout: float = None) -> bool:
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while not condition() and time.monotonic() < deadline:
            time.sleep(0.002)
        return bool(condition())

    def test_fields_of_a_block_are_never_sent_half_written(self):
        motor = tx_motor(tx=Timing(0.002))
        self.start(motor)
        for i in range(1, 6):
            with motor.update():
                motor.speed = i * 100
                time.sleep(0.01)                             # several periods pass in the middle of the block
                motor.cmd.mode = i
        time.sleep(0.01)
        packets = [(p.speed, p.cmd.mode) for p in self.sent_motors()]
        self.assertTrue(any(pair == (500, 5) for pair in packets))
        self.assertEqual([pair for pair in packets if pair[0] != pair[1] * 100], [(0, 1)] * packets.count((0, 1)))

    def test_fields_written_with_update_are_never_mixed(self):
        motor = tx_motor(tx=Timing(0.001))
        self.start(motor)
        for i in range(300):
            motor.update({"speed": i, "cmd.mode": i % 8})
        time.sleep(0.02)
        mixed = [(p.speed, p.cmd.mode) for p in self.sent_motors() if p.speed % 8 != p.cmd.mode]
        self.assertEqual(mixed, [(0, 1)] * len(mixed))        # only the packets before the first update

    def test_request_bit_written_during_a_send_is_not_lost(self):          # B12
        motor = tx_motor(tx=Timing(0.01))
        self.backend.holding = True
        self.start(motor)
        self.assertTrue(self.backend.entered.wait(self.timeout))           # the TX thread is inside the request
        writer = threading.Thread(target=motor.update, args=({"cmd.startReq": 1},))
        writer.start()
        time.sleep(0.02)
        self.assertTrue(writer.is_alive())                                 # waits for the send to finish
        self.backend.release()
        writer.join(self.timeout)
        self.assertTrue(self.wait_until(lambda: any(p.cmd.startReq for p in self.sent_motors())))
        self.assertTrue(self.wait_until(lambda: motor.cmd.startReq == 0))  # cleared after it went out

    def test_snapshot_never_sees_half_a_block(self):
        motor = tx_motor()
        seen = []

        def reader():
            seen.append(motor.snapshot())

        with motor.update():
            motor.speed = 100
            thread = threading.Thread(target=reader)
            thread.start()
            time.sleep(0.02)
            motor.cmd.mode = 1 + 1
        thread.join(self.timeout)
        self.assertEqual((seen[0].speed, seen[0].cmd.mode), (100, 2))

    def test_snapshot_of_an_rx_message_does_not_wait(self):
        status = motor_cmd(DEST, SRC, 0x30)
        with status.update():
            thread = threading.Thread(target=status.snapshot)
            thread.start()
            thread.join(0.5)
            self.assertFalse(thread.is_alive())

    def test_send_inside_a_block(self):
        motor = tx_motor()
        with motor.update():
            motor.speed = 42
            self.assertTrue(self.comm.send(motor))
        self.assertEqual(self.sent_motors()[-1].speed, 42)

    def test_long_block_delays_only_its_own_message(self):
        motor = tx_motor(tx=Timing(0.005))
        other = comut(SRC, DEST, 0x21, direction=Direction.TX, tx=Timing(0.005))    # same channel
        self.start(motor)
        self.start(other)
        time.sleep(0.02)
        with motor.update():
            before = (motor.peek_sent(), other.peek_sent())
            time.sleep(0.1)
            during = (motor.peek_sent() - before[0], other.peek_sent() - before[1])
        self.assertEqual(during[0], 0)
        self.assertGreaterEqual(during[1], 12)
        self.assertTrue(self.wait_until(lambda: motor.peek_sent() > before[0]))     # goes on after the block

    def test_one_shot_send_waits_for_the_block(self):
        motor = tx_motor()
        done = threading.Event()
        with motor.update():
            motor.speed = 1
            thread = threading.Thread(target=lambda: (self.comm.send(motor), done.set()))
            thread.start()
            time.sleep(0.02)
            self.assertFalse(done.is_set())
            motor.cmd.mode = 7
        thread.join(self.timeout)
        self.assertEqual((self.sent_motors()[-1].speed, self.sent_motors()[-1].cmd.mode), (1, 7))


if __name__ == "__main__":
    unittest.main()
