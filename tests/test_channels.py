"""Unit tests of channels and framing: no threads, no UTS."""

__author__ = "İsmail Baysal"

import unittest

from asl_testing import (ChannelSet, EthernetChannel, EthernetProtocol, Framing, Mil1553Channel, Mil1553Protocol,
                         Rs422Channel, Rs422Protocol)
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
    def test_default_protocol_of_each_channel_type(self):
        self.assertIsInstance(EthernetChannel(1).protocol, EthernetProtocol)
        self.assertIsInstance(Rs422Channel(1).protocol, Rs422Protocol)
        self.assertIsInstance(Mil1553Channel(1).protocol, Mil1553Protocol)

    def test_each_channel_has_its_own_protocol_object(self):
        self.assertIsNot(Rs422Channel(1).protocol, Rs422Channel(2).protocol)

    def test_protocol_given_with_the_channel(self):
        ch = Mil1553Channel(4, protocol=Mil1553Protocol(byte_order="big"))
        self.assertEqual((ch.protocol.byte_order, ch.key, str(ch)), ("big", ("mil1553", 4), "mil1553:4"))


class EthHeaderTests(unittest.TestCase):
    def test_roundtrip(self):
        header = EthHeader()
        self.assertEqual(header.on_receive(header.on_send(b"abc")), b"abc")

    def test_foreign_packet_is_not_accepted(self):
        self.assertIsNone(EthHeader().on_receive(bytes(10)))


if __name__ == "__main__":
    unittest.main()
