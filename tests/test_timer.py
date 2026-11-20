"""Windows timer resolution: set while a Comm is open, given back when the last one closes."""

__author__ = "İsmail Baysal"

import unittest
from unittest import mock

from asl_testing.runtime import timer
from tests.base import open_comm
from tests.settings import make_adapter


class FakeWinmm:
    def __init__(self):
        self.calls = []

    def timeBeginPeriod(self, ms):
        self.calls.append(("begin", ms))

    def timeEndPeriod(self, ms):
        self.calls.append(("end", ms))


class TimerTests(unittest.TestCase):
    def setUp(self):
        self.winmm = FakeWinmm()
        patches = [mock.patch.object(timer.sys, "platform", "win32"),
                   mock.patch.object(timer, "_winmm", lambda: self.winmm),
                   mock.patch.object(timer, "_users", 0)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_comm_sets_it_while_open(self):
        comm = open_comm(make_adapter())
        self.assertEqual(self.winmm.calls, [("begin", 1)])
        comm.close()
        comm.close()                                        # a second close does not end it twice
        self.assertEqual(self.winmm.calls, [("begin", 1), ("end", 1)])

    def test_two_comms_share_it(self):
        first, second = open_comm(make_adapter()), open_comm(make_adapter())
        first.close()
        self.assertEqual(self.winmm.calls, [("begin", 1)])  # still needed by the second one
        second.close()
        self.assertEqual(self.winmm.calls, [("begin", 1), ("end", 1)])

    def test_nothing_outside_windows(self):
        with mock.patch.object(timer.sys, "platform", "linux"):
            open_comm(make_adapter()).close()
        self.assertEqual(self.winmm.calls, [])


if __name__ == "__main__":
    unittest.main()
