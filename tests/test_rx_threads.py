"""One RX thread per channel: a channel whose request hangs does not hold up the others."""

__author__ = "İsmail Baysal"

import threading
import time

from asl_testing import Direction, FakeUtsAdapter, RxTimeout, Timing
from projects.example_project.channels import MyChannels
from projects.example_project.messages import bambaşka, comut
from tests.base import CommTestCase, open_comm
from tests.settings import DEST, SRC

CONTROL, DIAG = MyChannels.CONTROL, MyChannels.DIAG


class HangingUtsAdapter(FakeUtsAdapter):
    """GET on the channels in `hanging` does not return until release() is called."""

    def __init__(self):
        super().__init__()
        self.hanging: set = set()
        self._released = threading.Event()

    def release(self) -> None:
        self._released.set()

    def get(self, path, interface, timeout=0.0):
        if (path, interface) in {(self.protocol(ch).path, ch.interface) for ch in self.hanging}:
            self._released.wait()
        return super().get(path, interface, timeout)


class RxThreadTests(CommTestCase):
    def setUp(self):
        self.adapter = HangingUtsAdapter()
        self.comm = open_comm(self.adapter)
        self.addCleanup(self.comm.close)
        self.addCleanup(self.adapter.release)                  # runs first, so close() can join the threads

    def rx_threads(self) -> list[str]:
        return sorted(t.name for t in threading.enumerate() if t.name.startswith("Rx-"))

    def wait_until(self, condition) -> bool:
        deadline = time.monotonic() + self.timeout
        while not condition() and time.monotonic() < deadline:
            time.sleep(0.005)
        return bool(condition())

    def test_hanging_channel_does_not_delay_another_channel(self):
        self.adapter.hanging.add(CONTROL)
        comut(DEST, SRC, 0x20)                             # CONTROL is polled, and hangs
        diag = bambaşka(0x07, SRC, 0x40)
        diag.has_new()
        time.sleep(0.05)                                   # CONTROL is inside its request now
        started = time.monotonic()
        self.device_sends(bambaşka(0x07, SRC, 0x40, direction=Direction.TX, request=(1, 2, 3, 4)))
        self.expect_new(diag, timeout=0.3)
        self.assertLess(time.monotonic() - started, 0.3)

    def test_timeouts_are_checked_while_a_channel_hangs(self):
        timeouts = []
        self.comm.subscribe(RxTimeout, timeouts.append)
        self.adapter.hanging.add(CONTROL)
        hanging = comut(DEST, SRC, 0x20, rx=Timing(0.05, tolerance=2))
        diag = bambaşka(0x07, SRC, 0x40, rx=Timing(0.05, tolerance=2))
        for _ in range(12):                                # the device keeps sending on DIAG
            self.device_sends(bambaşka(0x07, SRC, 0x40, direction=Direction.TX))
            time.sleep(0.025)
        time.sleep(0.05)
        late = [ev.message for ev in timeouts]
        self.assertTrue(any(m is hanging for m in late))   # found by the watchdog while its channel hangs
        self.assertFalse(any(m is diag for m in late))

    def test_channel_gets_its_thread_when_its_first_rx_message_is_defined(self):
        self.assertEqual(self.rx_threads(), [])
        comut(DEST, SRC, 0x20)
        self.assertTrue(self.wait_until(lambda: self.rx_threads() == ["Rx-CONTROL"]))
        self.comm.listen(DIAG)
        self.assertTrue(self.wait_until(lambda: self.rx_threads() == ["Rx-CONTROL", "Rx-DIAG"]))

    def test_thread_ends_when_the_channel_is_no_longer_needed(self):
        comut(DEST, SRC, 0x20)
        self.assertTrue(self.wait_until(lambda: self.rx_threads() == ["Rx-CONTROL"]))
        type(comut(DEST, SRC, 0x20)).clear_registry()
        self.assertTrue(self.wait_until(lambda: self.rx_threads() == []))

    def test_close_ends_every_rx_thread(self):
        comut(DEST, SRC, 0x20)
        self.comm.listen(DIAG)
        self.assertTrue(self.wait_until(lambda: len(self.rx_threads()) == 2))
        self.comm.close()
        alive = [t.name for t in threading.enumerate() if t.name.startswith("Rx")]
        self.assertEqual(alive, [])

    def test_packets_of_one_channel_keep_their_order(self):
        status = comut(DEST, SRC, 0x20)
        mark = status.rx_history.mark()
        for value in range(20):
            self.device_sends(comut(DEST, SRC, 0x20, direction=Direction.TX, comut=(value, 0)))
        self.assertTrue(self.wait_until(lambda: len(status.rx_history.since(mark)) == 20))
        self.assertEqual([r.snapshot().comut[0] for r in status.rx_history.since(mark)], list(range(20)))


if __name__ == "__main__":
    import unittest
    unittest.main()
