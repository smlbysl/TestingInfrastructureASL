"""Base test classes: every test starts from the same clean state.

CommTestCase      runs everywhere (the UTS client comes from tests/settings.make_uts)
HardwareTestCase  same, but only runs when ASL_HARDWARE=1 is set; otherwise skipped

Each test:
- clears the registry of the projects (messages of earlier tests are dropped,
  so create messages inside the test or in setUp, not at module level)
- gets a new UTS client and a new, opened Comm (self.comm)
- stops its periodic messages and closes Comm at the end, even if it fails

Environment:
    ASL_HARDWARE=1     run HardwareTestCase tests
    ASL_TIMEOUT=1.0    default wait time of the expect_* helpers (seconds)
"""

__author__ = "İsmail Baysal"

import os
import unittest

from asl_testing import Comm
from tests.settings import PROJECTS, make_uts

HARDWARE = os.environ.get("ASL_HARDWARE") == "1"
TIMEOUT = float(os.environ.get("ASL_TIMEOUT", "1.0"))


def open_comm(uts) -> Comm:
    """Clean registry, opened Comm on the given UTS client (shared by the base classes and conftest.py)."""
    for project in PROJECTS:
        project.clear_registry()
    comm = Comm(uts, PROJECTS)
    comm.open()
    return comm


class CommTestCase(unittest.TestCase):
    timeout = TIMEOUT

    def setUp(self):
        self.uts = make_uts()
        self.comm = open_comm(self.uts)
        self.addCleanup(self.comm.close)

    # ---------------------------------------------------------------- helpers

    def start(self, msg) -> None:
        """Starts a periodic message; it is stopped when the test ends."""
        self.comm.start(msg)
        self.addCleanup(self.comm.stop, msg)

    def send(self, msg) -> None:
        """Sends msg once; fails the test if the send fails."""
        self.assertTrue(self.comm.send(msg), f"{type(msg).__name__} could not be sent")

    def expect_new(self, msg, timeout: float = None) -> int:
        """Waits for a new valid packet of msg; fails the test on timeout. Returns the count."""
        timeout = self.timeout if timeout is None else timeout
        count = self.comm.wait_new(msg, timeout=timeout)
        self.assertGreater(count, 0, f"{type(msg).__name__} not received within {timeout} s")
        return count

    def expect_sent(self, msg, timeout: float = None) -> int:
        """Waits for a successful send of msg; fails the test on timeout. Returns the count."""
        timeout = self.timeout if timeout is None else timeout
        count = self.comm.wait_sent(msg, timeout=timeout)
        self.assertGreater(count, 0, f"{type(msg).__name__} not sent within {timeout} s")
        return count

    def device_sends(self, msg) -> None:
        """Simulation only (FakeUtsClient): msg arrives as if the device had sent it."""
        ch = msg.channel
        self.uts.inject(ch.protocol, ch.interface, ch.framing.envelope.on_send(msg.pack()))


@unittest.skipUnless(HARDWARE, "hardware tests: set ASL_HARDWARE=1")
class HardwareTestCase(CommTestCase):
    """Base for tests that run against the real target. Skipped unless ASL_HARDWARE=1."""
