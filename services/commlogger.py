"""CommLogger: writes the messaging history (every received and sent packet) to one CSV file.

One subscription to all events on a single thread, so lines stay in publish order.
The bytes on the line (wire) are logged, so any field can be decoded later with the message class,
even fields nobody watched during the test.

Columns: host_time, uts_time, direction, link, channel, message, signature, length, data
"""
import csv
from datetime import datetime
from typing import Optional

from events.types import InvalidReceived, MessageReceived, MessageSent, UnknownReceived

HEADER = ["host_time", "uts_time", "direction", "link", "channel", "message", "signature", "length", "data"]
DIRECTIONS = {
    MessageReceived: "RX",
    MessageSent: "TX",
    InvalidReceived: "RX-INVALID",
    UnknownReceived: "RX-UNKNOWN",
}


class CommLogger:
    def __init__(self, comm, path):
        self.path = path
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(HEADER)
        self._sub = comm.subscribe(object, self._on_event)

    def _on_event(self, event) -> None:
        direction = DIRECTIONS.get(type(event))
        if direction is None:
            return                                  # not a message event
        msg = getattr(event, "message", None)
        if msg is not None:
            channel, link = msg._channel, msg._channel.link
        else:
            channel, link = event.channel, event.link
        self._writer.writerow([
            _host_time(event.host_time),
            _uts_time(getattr(event, "timestamp", None)),
            direction,
            link.name if link is not None else "",
            channel.name if channel is not None else "",
            type(msg).__name__ if msg is not None else "",
            f"0x{msg._signature_id:X}" if msg is not None and msg._signature_id is not None else "",
            len(event.wire),
            event.wire.hex(" "),
        ])
        self._file.flush()

    def close(self) -> None:
        """Called by Comm.close() after the bus has delivered every queued event."""
        self._file.close()


def _host_time(t: float) -> str:
    return datetime.fromtimestamp(t).isoformat(sep=" ", timespec="milliseconds")


def _uts_time(t: Optional[float]) -> str:
    return "" if t is None else f"{t:.6f}"
