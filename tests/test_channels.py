"""Unit tests of channels and byte-stream headers: no threads, no UTS."""
import unittest

from asl_testing import NO_PCI, EthernetChannel, Rs422Channel
from asl_testing.channel.channel import check_channels
from projects.example_project.framing import EthHeader


class ChannelRuleTests(unittest.TestCase):
    def test_two_plain_channels_on_one_address_are_rejected(self):
        with self.assertRaises(ValueError):
            check_channels([EthernetChannel(1), EthernetChannel(1)])

    def test_one_plain_and_one_with_header_is_allowed(self):
        check_channels([EthernetChannel(1, header=EthHeader()), EthernetChannel(1)])

    def test_same_interface_on_another_bus_is_another_address(self):
        check_channels([EthernetChannel(1), Rs422Channel(1)])


class EthHeaderTests(unittest.TestCase):
    def test_roundtrip(self):
        header = EthHeader()
        self.assertEqual(header.decode(header.encode(NO_PCI, b"abc")), (NO_PCI, b"abc"))

    def test_foreign_packet_is_not_accepted(self):
        self.assertIsNone(EthHeader().decode(bytes(10)))


if __name__ == "__main__":
    unittest.main()
