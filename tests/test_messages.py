"""Unit tests of the message model: no threads, no UTS."""
import unittest

from asl_testing import Direction
from projects.example_project.messages import motor_cmd, request
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


if __name__ == "__main__":
    unittest.main()
