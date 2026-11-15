"""Unit tests of channels and framing: no threads, no UTS."""

__author__ = "İsmail Baysal"

import unittest

from asl_testing import ChannelSet, EthernetChannel, Framing, Mil1553Channel, Rs422Channel
from asl_testing.channel.channel import check_channels
from projects.example_project.framing import EthHeader


class ChannelRuleTests(unittest.TestCase):
    def test_one_interface_has_one_channel(self):
        for second in (EthernetChannel(1), EthernetChannel(1, Framing(envelope=EthHeader()))):
            with self.subTest(second=second), self.assertRaises(ValueError):
                check_channels([EthernetChannel(1), second])

    def test_same_number_on_other_protocols_is_another_interface(self):
        check_channels([EthernetChannel(1), Rs422Channel(1), Mil1553Channel(1)])

    def test_rule_is_checked_when_the_set_is_defined(self):
        with self.assertRaises(ValueError):
            class Twice(ChannelSet):
                A = Rs422Channel(3)
                B = Rs422Channel(3)


class ChannelProtocolTests(unittest.TestCase):
    def test_protocol_name_of_each_channel_type(self):
        self.assertEqual((EthernetChannel(1).protocol, Rs422Channel(1).protocol, Mil1553Channel(1).protocol),
                         ("ethernet", "rs422", "mil1553"))

    def test_byte_order_given_with_the_1553_channel(self):
        ch = Mil1553Channel(4, byte_order="big")
        self.assertEqual((ch.byte_order, ch.key, str(ch)), ("big", ("mil1553", 4), "mil1553:4"))
        self.assertEqual(Mil1553Channel(5).byte_order, "little")


class EthHeaderTests(unittest.TestCase):
    def test_roundtrip(self):
        header = EthHeader()
        self.assertEqual(header.on_receive(header.on_send(b"abc")), b"abc")

    def test_foreign_packet_is_not_accepted(self):
        self.assertIsNone(EthHeader().on_receive(bytes(10)))


if __name__ == "__main__":
    unittest.main()
