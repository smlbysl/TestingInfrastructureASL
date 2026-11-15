"""UtsAdapter: config and filters by channel or message, and what an adapter without them does."""

__author__ = "İsmail Baysal"

import unittest

from asl_testing import Adapter, AdapterError, FakeUtsAdapter, UtsAdapter
from projects.example_project.channels import MyChannels
from projects.example_project.messages import bambaşka, comut
from tests.base import CommTestCase
from tests.settings import DEST, SRC


class ConfigAndFilterTests(CommTestCase):
    def test_config_by_channel_or_message(self):
        status = comut(DEST, SRC, 0x20)
        self.comm.adapter.set_config(status, baudRate=115200)
        self.assertEqual(self.comm.adapter.get_config(MyChannels.CONTROL), {"baudRate": 115200})
        self.assertEqual(self.adapter.configs[("serials", 0)], {"baudRate": 115200})     # the UTS path

    def test_add_filter_once_and_after_the_envelope(self):
        status = comut(DEST, SRC, 0x20)
        diag = bambaşka(0x07, SRC, 0x40)
        self.comm.adapter.add_filter(status)
        self.comm.adapter.add_filter(status)                                   # second time: no change
        self.comm.adapter.add_filter(diag)
        kind, groups = self.comm.adapter.get_filter(status)
        self.assertEqual((kind, len(groups)), ("INCLUSIVE", 1))
        self.assertEqual(groups[0][0], (4, 1))                                 # destinationId at byte 4
        kind, groups = self.comm.adapter.get_filter(MyChannels.DIAG)
        self.assertEqual(groups[0][0], (8, 7))                                 # after the 8-byte header

    def test_remove_and_clear_filter(self):
        status = comut(DEST, SRC, 0x20)
        other = comut(DEST, SRC, 0x22)
        self.comm.adapter.add_filter(status)
        self.comm.adapter.add_filter(other)
        self.comm.adapter.remove_filter(status)
        self.assertEqual(len(self.comm.adapter.get_filter(status)[1]), 1)
        self.comm.adapter.remove_filter(other)
        self.assertEqual(self.comm.adapter.get_filter(status), ("NONE", []))  # no group left: no filter
        self.comm.adapter.add_filter(status)
        self.comm.adapter.clear_filter(MyChannels.CONTROL)
        self.assertEqual(self.comm.adapter.get_filter(status), ("NONE", []))

    def test_set_filter_writes_the_whole_filter(self):
        self.comm.adapter.set_filter(MyChannels.CONTROL, [[(4, 2)]])
        self.assertEqual(self.comm.adapter.get_filter(MyChannels.CONTROL), ("INCLUSIVE", [[(4, 2)]]))


class AdapterWithoutRequestsTests(unittest.TestCase):
    def test_adapter_without_config_and_filters(self):
        class BytesOnly(Adapter):
            def send(self, channel, wire):
                pass

            def receive(self, channel):
                return []

        with self.assertRaises(AdapterError):
            BytesOnly().add_filter(comut(DEST, SRC, 0x20))
        with self.assertRaises(AdapterError):
            BytesOnly().get_config(MyChannels.CONTROL)

    def test_uts_request_not_written_yet(self):
        class OnlyMessages(UtsAdapter):
            def post(self, path, interface, body, timeout):
                pass

            def get(self, path, interface, timeout):
                return []

        with self.assertRaises(NotImplementedError):
            OnlyMessages().get_config(MyChannels.CONTROL)

    def test_fake_is_a_uts_adapter(self):
        self.assertIsInstance(FakeUtsAdapter(), UtsAdapter)


if __name__ == "__main__":
    unittest.main()
