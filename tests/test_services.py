"""Services on the event bus: CSV log of the traffic (CommLogger) and the error file (ErrorLog)."""

__author__ = "İsmail Baysal"

import csv
import tempfile
import time
import unittest
from pathlib import Path

from asl_testing import CommLogger, Direction, ErrorLog, Timing
from projects.example_project.messages import comut, request
from tests.base import CommTestCase
from tests.settings import DEST, SRC


class CommLoggerTests(CommTestCase):
    def setUp(self):
        super().setUp()
        self.path = Path(tempfile.mkdtemp()) / "traffic.csv"
        self.logger = CommLogger(self.comm, self.path)

    def rows(self) -> list[list[str]]:
        self.comm.close()                                      # writes the queued events first
        self.logger.close()
        with self.path.open(encoding="utf-8") as f:
            return list(csv.reader(f))

    def test_sent_received_invalid_and_unknown_packets(self):
        rx = comut(DEST, SRC, 0x20)
        rx.has_new()
        self.send(request(SRC, DEST, 0x10, direction=Direction.TX))
        self.device_sends(comut(DEST, SRC, 0x20, direction=Direction.TX, comut=(5, 6)))
        self.expect_new(rx)
        ch = rx.channel
        bad = bytearray(comut(DEST, SRC, 0x20, direction=Direction.TX).pack())
        bad[-1] ^= 0xFF
        self.uts.inject(ch, bytes(bad))
        self.uts.inject(ch, b"\x99" * 12)
        deadline = time.monotonic() + self.timeout
        while len(self.comm.unknown) < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.05)

        header, *rows = self.rows()
        self.assertEqual(header, ["host_time", "uts_time", "direction", "channel", "message", "signature", "length",
                                  "data"])
        by_direction = {row[2]: row for row in rows}
        self.assertEqual(set(by_direction), {"TX", "RX", "RX-INVALID", "RX-UNKNOWN"})
        self.assertEqual(by_direction["TX"][3:5], ["CONTROL", "request"])
        self.assertEqual(by_direction["RX"][3:5], ["CONTROL", "comut"])
        self.assertEqual(by_direction["RX-UNKNOWN"][6:], ["12", "99 " * 11 + "99"])
        self.assertEqual(int(by_direction["RX"][6]), len(bytes.fromhex(by_direction["RX"][7])))


class ErrorLogTests(CommTestCase):
    def setUp(self):
        super().setUp()
        self.path = Path(tempfile.mkdtemp()) / "errors.log"
        self.errors = ErrorLog(self.comm, self.path)

    def text(self) -> str:
        self.comm.close()
        self.errors.close()
        return self.path.read_text(encoding="utf-8")

    def test_failed_send_is_written(self):
        def unreachable(*args):
            raise ConnectionError("UTS unreachable")

        self.uts.post = unreachable
        self.assertFalse(self.comm.send(request(SRC, DEST, 0x10, direction=Direction.TX)))
        time.sleep(0.05)
        text = self.text()
        self.assertIn("ERROR UTS send failed on CONTROL", text)
        self.assertIn("UTS unreachable", text)

    def test_rx_timeout_and_recovery_are_written(self):
        rx = comut(DEST, SRC, 0x20, rx=Timing(0.05))
        time.sleep(0.3)                                         # never arrives: timeout
        self.device_sends(comut(DEST, SRC, 0x20, direction=Direction.TX))
        self.expect_new(rx)
        time.sleep(0.05)
        text = self.text()
        self.assertIn("WARNING comut on CONTROL not received", text)
        self.assertIn("INFO comut on CONTROL received again", text)


if __name__ == "__main__":
    unittest.main()
