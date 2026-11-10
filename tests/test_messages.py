"""Unit tests of the message model: no threads, no UTS."""
import struct
import threading
import unittest

from asl_testing import Direction
from projects.example_project.messages import motor_cmd, request, ser_report
from tests.settings import DEST, SRC


class MessageUnitTests(unittest.TestCase):
    def test_pack_decode_roundtrip(self):
        src = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX)
        src.speed = -120
        dst = motor_cmd(DEST, SRC, 0x30)
        self.assertTrue(dst.decode(src.pack()))
        self.assertEqual(dst.speed, -120)

    def test_checksum_mismatch_is_rejected(self):
        raw = bytearray(request(SRC, DEST, 0x10).pack())
        raw[-1] ^= 0xFF
        self.assertFalse(request(DEST, SRC, 0x10).validate(bytes(raw)))

    def test_wire_size_matches_packed_length(self):
        msg = request(SRC, DEST, 0x10)
        self.assertEqual(msg.wire_size(), len(msg.pack()))

    def test_counter_increments_per_pack(self):
        msg = request(SRC, DEST, 0x10)
        first = msg.messageCounter.val
        msg.pack()
        self.assertEqual(msg.messageCounter.val, (first + 1) % 256)


class RxValidationTests(unittest.TestCase):
    """K1: a variable-size packet whose length field is too small is invalid, it never raises."""

    def _report(self, count=2):
        tx = ser_report(SRC, DEST, 0, direction=Direction.TX)
        tx.count = count
        return tx.pack()

    def _with_length(self, raw, length):
        data = bytearray(raw)
        struct.pack_into("<H", data, ser_report.messageLength.offset, length)
        return bytes(data)

    def test_length_too_small_is_invalid(self):
        rx = ser_report(DEST, SRC, 0)
        raw = self._report()
        for length in (0, 1, ser_report.messageLength.offset + 2):
            with self.subTest(length=length):
                self.assertFalse(rx.validate(self._with_length(raw, length)))

    def test_valid_sizes_still_accepted(self):
        rx = ser_report(DEST, SRC, 0)
        for count in (0, 2, 8):
            with self.subTest(count=count):
                self.assertTrue(rx.decode(self._report(count)))
                self.assertEqual(rx.count, count)


class OneCopyDecodeTests(unittest.TestCase):
    """B1: a reader running next to decode sees the old or the new packet, never a mix or zeros."""

    def test_no_torn_reads(self):
        a = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX)
        a.speed = 100
        b = motor_cmd(SRC, DEST, 0x30, direction=Direction.TX)
        b.speed = -100
        packets = (a.pack(), b.pack())
        m = motor_cmd(DEST, SRC, 0x30)
        m.decode(packets[0])
        stop, bad = threading.Event(), []

        def reader():
            while not stop.is_set():
                if m.speed not in (100, -100):
                    bad.append(m.speed)

        t = threading.Thread(target=reader)
        t.start()
        for i in range(20_000):
            m.decode(packets[i % 2])
        stop.set()
        t.join()
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
