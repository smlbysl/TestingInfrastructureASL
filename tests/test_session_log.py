"""SessionLog: the session folder (session.json + records.csv) that the monitor tool reads."""

__author__ = "İsmail Baysal"

import csv
import json
import tempfile
import time
import unittest
from pathlib import Path

from asl_testing import Direction, SessionLog, Timing
from asl_testing.services.session_log import HEADER
from projects.example_project.messages import comut, request
from tests.base import CommTestCase
from tests.settings import DEST, SRC


class SessionLogTests(CommTestCase):
    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp())
        self.log = SessionLog(self.comm, self.root, name="lab 1")

    def finish(self) -> list[dict]:
        self.comm.close()
        self.log.close()
        with self.log.path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def test_folder_and_session_json(self):
        self.assertTrue(self.log.folder.name.endswith("_lab_1"))
        info = json.loads((self.log.folder / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(info["status"], "running")
        self.assertEqual(info["catalog"]["projects"], ["projects.example_project.header:ProjectBase"])
        self.assertIn("projects.example_project.messages", info["catalog"]["modules"])
        self.finish()
        info = json.loads((self.log.folder / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(info["status"], "closed")
        self.assertIsNotNone(info["ended"])

    def test_packets_marks_errors_and_events(self):
        rx = comut(DEST, SRC, 0x20, rx=Timing(0.05))
        self.send(request(SRC, DEST, 0x10, direction=Direction.TX))
        self.log.mark("step 1,\nsecond line")
        time.sleep(0.3)                                                # comut never comes: RxTimeout
        self.device_sends(comut(DEST, SRC, 0x20, direction=Direction.TX))
        self.expect_new(rx)

        def unreachable(*args):
            raise ConnectionError("UTS unreachable")
        self.adapter.post = unreachable
        self.comm.send(request(SRC, DEST, 0x10, direction=Direction.TX))
        time.sleep(0.05)

        rows = self.finish()
        self.assertEqual(list(rows[0]), HEADER)
        kinds = [r["direction"] for r in rows]
        self.assertEqual(kinds[:2], ["TX", "MARK"])                    # mark keeps its place after the packet
        mark = rows[1]
        self.assertEqual(mark["note"], "step 1,\\nsecond line")         # one physical line
        self.assertIn("EVENT", kinds)
        self.assertIn("RxTimeout", [r["note"].split()[0] for r in rows if r["direction"] == "EVENT"])
        error = [r for r in rows if r["direction"] == "ERROR"][0]
        self.assertIn("UTS unreachable", error["note"])
        lines = self.log.path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), len(rows) + 1)                    # every record is one line

    def test_two_logs_in_the_same_second_get_their_own_folder(self):
        other = SessionLog(self.comm, self.root, name="lab 1")
        self.addCleanup(other.close)
        self.assertNotEqual(other.folder, self.log.folder)
        self.finish()


if __name__ == "__main__":
    unittest.main()
