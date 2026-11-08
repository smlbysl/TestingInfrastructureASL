"""CommTestCase: every test starts from the same clean state.

- the registry of the projects is cleared (messages from earlier tests are dropped)
- a new UTS and a new Comm are created and opened
- Comm is closed even when the test fails (addCleanup)
"""
import unittest

from asl_testing import Comm
from tests.settings import PROJECTS, make_uts


class CommTestCase(unittest.TestCase):
    def setUp(self):
        for project in PROJECTS:
            project.clear_registry()
        self.uts = make_uts()
        self.comm = Comm(self.uts, PROJECTS)
        self.comm.open()
        self.addCleanup(self.comm.close)

    def device_sends(self, wire_msg):
        """Makes the device send wire_msg: its bytes (with the channel header) arrive on the UTS."""
        ch = wire_msg.channel
        self.uts.inject(ch.protocol, ch.interface, ch.framing.envelope.on_send(wire_msg.pack()))
