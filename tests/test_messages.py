"""Unit tests of the message model: no threads, no UTS."""

__author__ = "İsmail Baysal"

import unittest

from asl_testing import Direction
from projects.example_project.messages import diag_log, motor_cmd, request
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

    # K1: a too small length field of a variable-size message is invalid, not a crash
    def _diag_with_length(self, length: int) -> bytes:
        tx = diag_log(SRC, DEST, 0x40, direction=Direction.TX)
        tx.count = 2
        raw = bytearray(tx.pack())
        offset = tx.messageLength.offset_in(tx)
        raw[offset:offset + 2] = length.to_bytes(2, "little")
        return bytes(raw)

    def test_too_small_length_is_invalid(self):
        rx = diag_log(DEST, SRC, 0x40)
        for length in (0, 1, rx.messageLength.min_length(rx) - 1):
            with self.subTest(length=length):
                self.assertFalse(rx.validate(self._diag_with_length(length)))

    def test_packet_shorter_than_length_field_is_invalid(self):
        with self.assertLogs("asl_testing.message.base", "ERROR"):
            self.assertFalse(diag_log(DEST, SRC, 0x40).validate(b"\x00" * 5))

    def test_valid_variable_size_still_accepted(self):
        tx = diag_log(SRC, DEST, 0x40, direction=Direction.TX)
        tx.count = 2
        self.assertTrue(diag_log(DEST, SRC, 0x40).validate(tx.pack()))


if __name__ == "__main__":
    unittest.main()
