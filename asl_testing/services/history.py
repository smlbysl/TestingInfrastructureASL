"""CommLogger: writes every received and sent packet to a CSV file.

One subscription to all events, so the lines keep publish order. Raw bytes are written, so any
field can be decoded later with the message class.

Columns: host_time, uts_time, direction, channel, message, signature, length, data
"""

__author__ = "İsmail Baysal"
import csv
from datetime import datetime
from typing import Optional

from asl_testing.comm import Comm
from asl_testing.events.types import InvalidReceived, MessageReceived, MessageSent, UnknownReceived

HEADER = ["host_time", "uts_time", "direction", "channel", "message", "signature", "length", "data"]
DIRECTIONS = {
    MessageReceived: "RX",
    MessageSent: "TX",
    InvalidReceived: "RX-INVALID",
    UnknownReceived: "RX-UNKNOWN",
}


class CommLogger:
    def __init__(self, comm: Comm, path: str):
        self.path = path
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(HEADER)
        self._sub = comm.subscribe(object, self._on_event)

    def _on_event(self, event) -> None:
        direction = DIRECTIONS.get(type(event))
        if direction is None:
            return
        msg = getattr(event, "message", None)
        self._writer.writerow([
            _host_time(event.host_time),
            _uts_time(getattr(event, "timestamp", None)),
            direction,
            str(event.channel) if event.channel is not None else "",
            type(msg).__name__ if msg is not None else "",
            f"0x{msg._signature_id:X}" if msg is not None and msg._signature_id is not None else "",
            len(event.raw),
            event.raw.hex(" "),
        ])
        self._file.flush()

    def close(self) -> None:
        """Call after comm.close(), so queued events are written first."""
        self._file.close()


def _host_time(t: float) -> str:
    return datetime.fromtimestamp(t).isoformat(sep=" ", timespec="milliseconds")


def _uts_time(t: Optional[float]) -> str:
    return "" if t is None else f"{t:.6f}"
