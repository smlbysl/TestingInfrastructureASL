"""Channel registry: registration rules and identification order (PCI, then signature). No threads."""
import unittest
from ctypes import LittleEndianStructure, c_uint8, c_uint16

from asl_testing import BaseMessageStructure, ChannelSet, Direction, EthernetChannel, NO_PCI, Pdu, Signature


class Ch(ChannelSet):
    ETH = EthernetChannel(5)


class Proj(BaseMessageStructure, LittleEndianStructure):
    _fields_ = [("kind", c_uint8)]
    _channel = Ch.ETH


class Signed(Proj):
    _signature = Signature("kind")


class a(Signed):
    _fields_ = [("value", c_uint16)]
    _defaults = {"kind": 1}


class b(Signed):
    _fields_ = [("value", c_uint16)]
    _defaults = {"kind": 2}


class plain(Proj):
    _fields_ = [("value", c_uint16)]


class RegistryTests(unittest.TestCase):
    def setUp(self):
        Proj.clear_registry()

    def test_signature_tells_messages_apart(self):
        ma, mb = a(), b()
        reg = Ch.ETH.registry
        self.assertIs(reg.identify(Pdu(NO_PCI, bytes([1, 0, 0]))), ma)
        self.assertIs(reg.identify(Pdu(NO_PCI, bytes([2, 0, 0]))), mb)
        self.assertIsNone(reg.identify(Pdu(NO_PCI, bytes([3, 0, 0]))))

    def test_message_without_signature_must_be_alone(self):
        a()
        with self.assertRaises(ValueError):
            plain()

    def test_nothing_after_a_message_without_signature(self):
        plain()
        with self.assertRaises(ValueError):
            a()

    def test_message_without_signature_takes_every_packet(self):
        mp = plain()
        self.assertIs(Ch.ETH.registry.identify(Pdu(NO_PCI, bytes(3))), mp)

    def test_same_signature_twice_is_a_conflict(self):
        class a2(Signed):
            _fields_ = [("value", c_uint16)]
            _defaults = {"kind": 1}
        a()
        with self.assertRaises(ValueError):
            a2()

    def test_created_again_replaces_the_old_object(self):
        old = a()
        new = a()
        self.assertFalse(old._registered)
        self.assertIs(Ch.ETH.registry.identify(Pdu(NO_PCI, bytes([1, 0, 0]))), new)

    def test_tx_objects_do_not_take_packets(self):
        a(direction=Direction.TX)
        self.assertIsNone(Ch.ETH.registry.identify(Pdu(NO_PCI, bytes([1, 0, 0]))))

    def test_unknown_address_field_is_rejected(self):
        with self.assertRaises(TypeError):
            Ch.ETH.protocol.make_pci(node=1)


if __name__ == "__main__":
    unittest.main()
