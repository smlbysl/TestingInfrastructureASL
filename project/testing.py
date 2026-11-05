"""Test support for the project, usable from unittest, pytest and own scripts.

- shared_comm(): loads and opens the environment once per process; every test uses the same Comm.
  The setup file comes from the SETUP environment variable (default: setups/fake.toml).
- CommTestCase: base class; self.comm in every test, comm.reset() after every test.
- baseline(comm): what must run during every test; edit for the project.
- device_send(): plays the device side on the fake UTS.
"""
import atexit
import os
import time
import unittest
from typing import Callable, Optional

from comm import Comm, FakeUtsClient
from generic.basemessage import BaseMessageStructure
from generic.enumerations import Direction
from generic.timing import Timing
from project.channels import MyChannels
from project.project import Family1, ProjectBase

DEFAULT_SETUP = "setups/fake.toml"

_comm: Optional[Comm] = None


def load_comm(setup: Optional[str] = None) -> Comm:
    """A new, not yet opened Comm for this project."""
    return Comm.load(setup or os.environ.get("SETUP", DEFAULT_SETUP), ProjectBase, MyChannels)


heartbeat: Optional[BaseMessageStructure] = None


def baseline(comm: Comm) -> None:
    """Started once after open; reset() brings it back after every test."""
    global heartbeat
    heartbeat = Family1(0x01, 0x02, 0x30, direction=Direction.TX, tx=Timing(0.1))
    comm.start(heartbeat)


def shared_comm() -> Comm:
    """The Comm of this process: loaded, opened and baselined on first use, closed at exit."""
    global _comm
    if _comm is None:
        _comm = load_comm()
        _comm.open()
        baseline(_comm)
        _comm.mark_baseline()
        atexit.register(_comm.close)
    return _comm


class CommTestCase(unittest.TestCase):
    comm: Comm

    @classmethod
    def setUpClass(cls):
        cls.comm = shared_comm()

    def tearDown(self):
        self.comm.reset()


# ---------------------------------------------------------------- helpers

def device_send(comm: Comm, msg: BaseMessageStructure, timestamp: Optional[float] = None) -> bytes:
    """Fake UTS only: puts msg on its link as if the device had sent it; returns the bytes on the line."""
    if not isinstance(comm.uts, FakeUtsClient):
        raise RuntimeError("device_send needs the fake UTS (setups/fake.toml)")
    wire = msg._channel.envelope.on_send(msg.pack())
    comm.uts.inject(msg._channel.link, wire, timestamp)
    return wire


def wait_until(condition: Callable[[], bool], timeout: float = 1.0, step: float = 0.005) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(step)
    return condition()
