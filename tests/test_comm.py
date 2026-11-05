"""Tests of the communication layer on the fake UTS. Run with either:

    python -m unittest discover -s tests -t .
    python -m pytest tests
"""
import time

from comm import Comm, FakeUtsClient
from comm.link import Link
from generic.channel import Channel, ChannelSet
from generic.enumerations import Direction
from generic.timing import Timing
from project import testing
from project.channels import MyChannels
from project.messages import bambaşka, comut, request
from project.testing import CommTestCase, device_send, wait_until

SRC, DEST = 0x01, 0x02


class SendReceiveTests(CommTestCase):
    def test_send_goes_to_the_link_of_the_channel(self):
        req = request(SRC, DEST, 0x10, direction=Direction.TX)
        before = len(self.comm.uts.sent)
        self.assertTrue(self.comm.send(req))
        link, wire = self.comm.uts.sent[before]
        self.assertIs(link, MyChannels.CONTROL.link)
        self.assertEqual(wire, bytes(req))

    def test_received_packet_is_written_into_the_object(self):
        status = comut(DEST, SRC, 0x20)
        remote = comut(DEST, SRC, 0x20, direction=Direction.TX)
        remote.comut[0] = 0xCAFE
        device_send(self.comm, remote, timestamp=123.5)
        self.assertTrue(wait_until(lambda: status.comut[0] == 0xCAFE))
        self.assertEqual(status.rx_state.timestamp, 123.5)

    def test_listener_runs_with_a_snapshot(self):
        status = comut(DEST, SRC, 0x20)
        seen = []
        self.comm.on_receive(status, lambda ev: seen.append(ev.snapshot().comut[1]))
        remote = comut(DEST, SRC, 0x20, direction=Direction.TX)
        remote.comut[1] = 7
        device_send(self.comm, remote)
        self.assertTrue(wait_until(lambda: seen == [7]))

    def test_unknown_and_invalid_packets(self):
        status = comut(DEST, SRC, 0x20)
        self.comm.uts.inject(MyChannels.CONTROL.link, bytes(16))
        remote = comut(DEST, SRC, 0x20, direction=Direction.TX)
        bad = bytearray(remote.pack())
        bad[-1] ^= 0xFF
        self.comm.uts.inject(MyChannels.CONTROL.link, bytes(bad))
        self.assertTrue(wait_until(lambda: len(self.comm.unknown) == 1 and status.rx_state.errors == 1))


class FramingTests(CommTestCase):
    def test_envelope_is_added_on_send_and_removed_on_receive(self):
        out = bambaşka(0x07, SRC, 0x40, direction=Direction.TX)
        before = len(self.comm.uts.sent)
        self.comm.send(out)
        _, wire = self.comm.uts.sent[before]
        self.assertEqual(wire[:2], b"\x55\xAA")
        self.assertEqual(wire[8:], bytes(out))

        diag = bambaşka(0x07, SRC, 0x40)
        remote = bambaşka(0x07, SRC, 0x40, direction=Direction.TX)
        remote.request[0] = 0x1234
        device_send(self.comm, remote)
        self.assertTrue(wait_until(lambda: diag.request[0] == 0x1234))

    def test_packet_without_header_goes_to_the_plain_channel(self):
        self.comm.uts.inject(MyChannels.DIAG.link, b"\x01\x02\x03")
        self.assertTrue(wait_until(lambda: len(self.comm.unknown) == 1))
        self.assertIs(self.comm.unknown[0].channel, MyChannels.RAW)

    def test_raw_rule_can_drop_packets(self):
        status = comut(DEST, SRC, 0x20)
        MyChannels.CONTROL.on_receive_raw(lambda data: None)
        device_send(self.comm, comut(DEST, SRC, 0x20, direction=Direction.TX))
        time.sleep(0.05)
        self.assertEqual(status.rx_state.count, 0)


class BaselineTests(CommTestCase):
    def test_reset_stops_periodic_started_in_a_test(self):
        cmd = request(SRC, DEST, 0x11, direction=Direction.TX, tx=Timing(0.01))
        self.comm.start(cmd)
        self.comm.reset()
        self.assertFalse(self.comm.is_running(cmd))

    def test_reset_restarts_and_restores_the_baseline(self):
        hb = testing.heartbeat
        self.comm.stop(hb)
        hb.messageId = 0x99
        counter = hb.messageCounter.val
        self.comm.reset()
        self.assertTrue(self.comm.is_running(hb))
        self.assertEqual(hb.messageId, 0x30)                     # baseline value
        self.assertGreaterEqual(hb.messageCounter.val, counter)  # counter keeps counting

    def test_reset_removes_listeners_callouts_and_rules(self):
        status = comut(DEST, SRC, 0x20)
        subscribers = len(self.comm.bus.subscribers())
        self.comm.on_receive(status, print)
        status.on_receive(print)
        MyChannels.CONTROL.on_send_raw(lambda d: d)
        self.comm.reset()
        self.assertEqual(len(self.comm.bus.subscribers()), subscribers)
        self.assertEqual(status._on_receive, [])
        self.assertEqual(MyChannels.CONTROL._tx_rules, [])

    def test_recreating_a_message_does_not_conflict(self):
        comut(DEST, SRC, 0x20)
        comut(DEST, SRC, 0x20)                  # replaces the first one, no error


class ConfigModeTests(CommTestCase):
    """Uses its own Comm and channel set so the shared one is not touched."""

    def _comm(self, mode, preset=None, **settings):
        class OwnChannels(ChannelSet):
            ONLY = Channel("SER9")

        link = Link.from_config("SER9", {"bus": "serials", "interface": 9, **settings}, mode)
        uts = FakeUtsClient()
        if preset:
            uts.preset("serials", 9, preset)
        OwnChannels.bind({"SER9": link})
        return Comm(uts, [], {"SER9": link}, OwnChannels), link, uts

    def test_auto_writes_the_setup_settings(self):
        comm, link, uts = self._comm("auto", baud_rate=115200)
        with comm:
            self.assertEqual(uts.configs[("serials", 9)]["baudRate"], 115200)

    def test_manual_keeps_and_reads_the_uts_settings(self):
        comm, link, uts = self._comm("manual", preset={"baudRate": 57600, "bufferSize": 5}, baud_rate=115200)
        with self.assertLogs("comm.comm", "WARNING"):
            comm.open()
        comm.close()
        self.assertEqual(link.baud_rate, 57600)
        self.assertEqual(link.buffer_size, 5)
