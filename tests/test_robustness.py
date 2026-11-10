"""Regressions found by the code review of the PDU / history refactor."""
import time
import unittest
from ctypes import LittleEndianStructure, c_uint8, c_uint16

from asl_testing import (BaseMessageStructure, ChannelSet, Direction, EthernetChannel, LinkError, Mil1553Channel,
                         Signature, Splitter, Timing)
from projects.example_project.types import CRC16, CmdByte, Length16
from tests.base import CommTestCase

LIVE: list = []


class HookCRC(CRC16):
    """A checksum whose computation lets "another thread" write the live object meanwhile."""

    def compute(self, data: bytes) -> int:
        if LIVE:
            LIVE[0].cmd.mode = 5
        return super().compute(data)


class Ch(ChannelSet):
    A = EthernetChannel(21)
    B = EthernetChannel(22)
    BUS = Mil1553Channel(23)


class SplitInTwo(Splitter):
    def split(self, data: bytes) -> list[bytes]:
        return [data[i:i + 2] for i in range(0, len(data), 2)]


class Split(ChannelSet):
    HDR = EthernetChannel(24, header=None)          # placeholder, replaced below
    RAW = EthernetChannel(25, splitter=SplitInTwo())


class Proj(BaseMessageStructure, LittleEndianStructure):
    _channel = Ch.A


class with_cmd(Proj):
    _fields_ = [("cmd", CmdByte), ("value", c_uint16), ("checksum", HookCRC)]
    _direction = Direction.TX


class var_attr(Proj):
    """Variable size whose body_size uses an attribute set in __init__."""
    _fields_ = [("length", Length16), ("data", c_uint8 * 8), ("checksum", CRC16)]
    _variable_size = True

    def __init__(self, n: int = 3, **kw):
        self.n = n
        super().__init__(**kw)

    def body_size(self) -> int:
        return var_attr.data.offset + self.n


class Bus(BaseMessageStructure, LittleEndianStructure):
    _channel = Ch.BUS


class NodeFamily(Bus):
    _address = {"node": 4}


class at_subnet(NodeFamily):
    _address = {"subnet": 2}
    _fields_ = [("w", c_uint16)]


class PackTests(unittest.TestCase):
    def tearDown(self):
        LIVE.clear()
        Proj.clear_registry()
        Bus.clear_registry()

    def test_concurrent_write_to_a_non_computed_special_field_is_kept(self):
        m = with_cmd()
        LIVE.append(m)
        m.pack()
        self.assertEqual(m.cmd.mode, 5)

    def test_hooks_and_body_size_see_object_attributes(self):
        m = var_attr(n=5, direction=Direction.TX, channel=Ch.B)
        packet = m.pack()
        self.assertEqual(len(packet), var_attr.data.offset + 5 + 2)
        self.assertEqual(m.length.val, len(packet))

    def test_address_is_merged_over_the_hierarchy(self):
        self.assertEqual(str(at_subnet().pci), "node=4 subnet=2")


class TxRobustnessTests(CommTestCase):
    def test_exception_in_a_callout_does_not_stop_periodic_sending(self):
        broken = with_cmd(tx=Timing(0.01))
        broken.on_send(lambda m: 1 / 0)
        good = with_cmd(channel=Ch.B, tx=Timing(0.01))
        errors = []
        self.comm.subscribe(LinkError, errors.append)
        self.start(broken)
        self.start(good)
        self.assertFalse(self.comm.send(broken))
        self.assertGreaterEqual(self.comm.wait_sent(good, timeout=0.5), 1)
        self.assertTrue(self.comm.tx._thread.is_alive())
        time.sleep(0.05)
        self.assertEqual(errors, [])                     # not a UTS error
        Proj.clear_registry()


class RxRobustnessTests(CommTestCase):
    def _good_after(self, bad_item):
        from projects.example_project.messages import comut
        from tests.settings import DEST, SRC
        errors = []
        self.comm.subscribe(LinkError, errors.append)
        status = comut(DEST, SRC, 0x20)
        ch = status.channel
        status.has_new()
        self.uts.inject(ch.protocol.path, ch.interface, bad_item)
        self.uts.device_sends(comut(DEST, SRC, 0x20, direction=Direction.TX))
        self.assertEqual(self.comm.wait_new(status, timeout=0.5), 1)
        deadline = time.monotonic() + 0.5
        while not errors and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(errors), 1)

    def test_message_that_is_an_int(self):
        self._good_after({"message": 5})

    def test_item_that_is_not_an_object(self):
        self._good_after([1, 2, 3])

    def test_timestamp_that_is_not_a_number(self):
        self._good_after({"message": [1, 2], "timestamp": "now"})


class SplitterTests(unittest.TestCase):
    def test_splitter_of_a_channel_without_rx_messages_applies(self):
        from asl_testing.runtime.transport import Transport
        from asl_testing.runtime.rx import RxPoller
        from asl_testing import FakeUtsClient

        class Hdr(BaseMessageStructure, LittleEndianStructure):
            _channel = Split.RAW

        class plain(Hdr):
            _fields_ = [("w", c_uint16)]

        class S2(ChannelSet):
            OTHER = EthernetChannel(25, header=_OneByteHeader())

        class Other(BaseMessageStructure, LittleEndianStructure):
            _channel = S2.OTHER

        class o(Other):
            _fields_ = [("b", c_uint8)]

        o()                                              # only the header channel has an RX message
        uts = FakeUtsClient()
        poller = RxPoller(Transport(uts), None, None, [Other], 1.0)
        addresses = poller.addresses()
        self.assertIn(Split.RAW, addresses[("ethernet", 25)])
        uts.inject("ethernet", 25, {"message": [0xB0, 7, 0xB0, 8]})
        frames = Transport(uts).poll(("ethernet", 25), addresses[("ethernet", 25)])
        self.assertEqual([f.pdu.sdu for f in frames], [b"\x07", b"\x08"])
        Other.clear_registry()


class _OneByteHeader:
    """A header B0 | sdu; packets without B0 belong to another channel."""
    from asl_testing import NoPci as pci_type
    offset = 1

    def encode(self, pci, sdu):
        return b"\xB0" + sdu

    def decode(self, data):
        from asl_testing import NO_PCI
        return (NO_PCI, data[1:]) if data[:1] == b"\xB0" else None


class MixedSignatureTests(unittest.TestCase):
    def test_different_signature_definitions_in_one_slot_are_warned(self):
        class S(ChannelSet):
            C = EthernetChannel(26)

        class P2(BaseMessageStructure, LittleEndianStructure):
            _channel = S.C
            _fields_ = [("x", c_uint8), ("y", c_uint8)]

        class FX(P2):
            _signature = Signature("x")

        class FY(P2):
            _signature = Signature("y")

        class mx(FX):
            _defaults = {"x": 1}

        class my(FY):
            _defaults = {"y": 2}

        mx()
        with self.assertLogs("asl_testing.channel.registry", level="WARNING"):
            my()
        P2.clear_registry()


if __name__ == "__main__":
    unittest.main()
