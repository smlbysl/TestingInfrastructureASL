"""Unit tests of channels and framing: no threads, no UTS."""
import unittest

from asl_testing import EthernetChannel, Framing
from projects.example_project.framing import EthHeader


class ChannelRuleTests(unittest.TestCase):
    def test_two_plain_channels_on_one_address_are_rejected(self):
        from asl_testing.channel.channel import check_channels
        with self.assertRaises(ValueError):
            check_channels([EthernetChannel(1), EthernetChannel(1)])

    def test_one_plain_and_one_with_envelope_is_allowed(self):
        from asl_testing.channel.channel import check_channels
        check_channels([EthernetChannel(1, Framing(envelope=EthHeader())), EthernetChannel(1)])


class EthHeaderTests(unittest.TestCase):
    def test_roundtrip(self):
        header = EthHeader()
        self.assertEqual(header.on_receive(header.on_send(b"abc")), b"abc")

    def test_foreign_packet_is_not_accepted(self):
        self.assertIsNone(EthHeader().on_receive(bytes(10)))


if __name__ == "__main__":
    unittest.main()
