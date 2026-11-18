"""SessionLog: writes a test run into a session folder, read by the monitor tool (asl_monitor, separate repo).

    log = SessionLog(comm, "runs", name="lab1")      # runs/2026-11-19_001500_lab1/
    log.mark("step 2: start motor")                  # a test step on the time line
    ...
    comm.close()
    log.close()                                      # status "closed": the monitor stops following

The folder holds:
    session.json    start / end time, status ("running" / "closed"), where the message classes are
    records.csv     one line per record, written and flushed at once (the monitor follows the file)

records.csv has the CommLogger columns and a `note` column at the end:
    host_time, uts_time, direction, channel, message, signature, length, data, note

    direction    data         note
    TX, RX       raw bytes
    RX-INVALID   raw bytes
    RX-UNKNOWN   raw bytes
    ERROR                     LinkError: operation and error text
    EVENT                     RxTimeout / RxRestored / RxOverflow (+ age)
    MARK                      text given to mark()

Every record is exactly one line: line breaks in a note are written as "\\n". The monitor uses the line
end to know that a record is complete. CommLogger is unchanged. Format: docs/SESSION_LOG.md.
"""

__author__ = "İsmail Baysal"
import csv
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from asl_testing.comm import Comm
from asl_testing.events.types import (InvalidReceived, LinkError, MessageReceived, MessageSent, RxOverflow,
                                      RxRestored, RxTimeout, UnknownReceived)

FORMAT = "asl-session"
FORMAT_VERSION = 1
HEADER = ["host_time", "uts_time", "direction", "channel", "message", "signature", "length", "data", "note"]
PACKETS = {
    MessageReceived: "RX",
    MessageSent: "TX",
    InvalidReceived: "RX-INVALID",
    UnknownReceived: "RX-UNKNOWN",
}


@dataclass(frozen=True)
class Mark:
    """A test step, published on the bus so it keeps its place among the packets."""
    text: str
    host_time: float


class SessionLog:
    def __init__(self, comm: Comm, root: str = "runs", name: str = "", projects: Optional[Sequence[type]] = None):
        self.comm = comm
        self.projects = list(projects if projects is not None else comm.projects)
        self.started = time.time()
        stamp = datetime.fromtimestamp(self.started).strftime("%Y-%m-%d_%H%M%S")
        self.folder = _new_folder(Path(root), f"{stamp}_{_slug(name)}" if name else stamp)
        self.name = name
        self.path = self.folder / "records.csv"
        self._lock = threading.Lock()                       # bus thread writes; mark() after close too
        self._file = open(self.path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file, lineterminator="\n")
        self._writer.writerow(HEADER)
        self._file.flush()
        self._closed = False
        self._write_session("running")
        self._sub = comm.subscribe(object, self._on_event)

    # ---------------------------------------------------------------- test API

    def mark(self, text: str) -> None:
        """Puts a test step on the time line (in order with the packets published before it)."""
        self.comm.bus.publish(Mark(str(text), time.time()))

    def close(self) -> None:
        """Call after comm.close(), so queued events are written first."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._file.close()
        self._write_session("closed")

    # ---------------------------------------------------------------- events

    def _on_event(self, event) -> None:
        row = self._row(event)
        if row is None:
            return
        with self._lock:
            if self._closed:
                return
            self._writer.writerow(row)
            self._file.flush()

    def _row(self, event) -> Optional[list]:
        direction = PACKETS.get(type(event))
        if direction is not None:
            msg = getattr(event, "message", None)
            return [_host_time(event.host_time), _uts_time(getattr(event, "timestamp", None)), direction,
                    _channel(event.channel),
                    type(msg).__name__ if msg is not None else "",
                    f"0x{msg._signature_id:X}" if msg is not None and msg._signature_id is not None else "",
                    len(event.raw), event.raw.hex(" "), ""]
        if isinstance(event, LinkError):
            return self._note_row(event.host_time, "ERROR", event.channel, None,
                                  f"UTS {event.operation} failed: {event.error!r}")
        if isinstance(event, RxTimeout):
            return self._note_row(event.host_time, "EVENT", event.message._channel, event.message,
                                  f"RxTimeout age={event.age:.3f}")
        if isinstance(event, RxRestored):
            return self._note_row(event.host_time, "EVENT", event.message._channel, event.message, "RxRestored")
        if isinstance(event, RxOverflow):
            return self._note_row(event.host_time, "EVENT", event.channel, None, "RxOverflow")
        if isinstance(event, Mark):
            return self._note_row(event.host_time, "MARK", None, None, event.text)
        return None

    @staticmethod
    def _note_row(host_time: float, direction: str, channel, msg, note: str) -> list:
        return [_host_time(host_time), "", direction, _channel(channel),
                type(msg).__name__ if msg is not None else "", "", "", "", _one_line(note)]

    # ---------------------------------------------------------------- session.json

    def _write_session(self, status: str) -> None:
        info = {
            "format": FORMAT,
            "formatVersion": FORMAT_VERSION,
            "name": self.name,
            "status": status,
            "started": _host_time(self.started),
            "ended": _host_time(time.time()) if status == "closed" else None,
            "records": self.path.name,
            "catalog": {
                "kind": "asl",
                "root": os.getcwd(),                        # import root of the project modules
                "projects": [f"{p.__module__}:{p.__qualname__}" for p in self.projects],
                "modules": _message_modules(self.projects),
            },
            "python": sys.version.split()[0],
        }
        tmp = self.folder / "session.json.tmp"
        tmp.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
        for _ in range(20):                                 # Windows: a reader may hold the file a moment
            try:
                os.replace(tmp, self.folder / "session.json")
                return
            except PermissionError:
                time.sleep(0.05)
        os.replace(tmp, self.folder / "session.json")


def _new_folder(root: Path, name: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    folder, n = root / name, 1
    while True:
        try:
            folder.mkdir()
            return folder
        except FileExistsError:
            n += 1
            folder = root / f"{name}_{n}"


def _message_modules(projects: Sequence[type]) -> list[str]:
    """Modules of every class below the projects (the monitor imports them to find classes by name)."""
    found, todo = [], list(projects)
    while todo:
        cls = todo.pop()
        if cls.__module__ not in found:
            found.append(cls.__module__)
        todo.extend(cls.__subclasses__())
    return found


def _slug(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name).strip("_") or "run"


def _one_line(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")


def _channel(channel) -> str:
    return str(channel) if channel is not None else ""


def _host_time(t: float) -> str:
    return datetime.fromtimestamp(t).isoformat(sep=" ", timespec="microseconds")


def _uts_time(t: Optional[float]) -> str:
    return "" if t is None else f"{t:.6f}"
