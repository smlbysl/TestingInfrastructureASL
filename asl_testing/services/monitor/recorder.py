"""Recorder: keeps every received / sent packet per message, decodes field values on request.

A message stream is identified by (direction, class name, channel, signature id).
Each stream keeps (time, image) pairs; image is the ctypes layout of the message, so any field
can be decoded later. Values are decoded only for the signals that are viewed.

Sources:
- live: MessageReceived / MessageSent events of a Comm (start / stop)
- offline: a CSV written by CommLogger; the class is found by its name in the projects
Times are seconds on this host's clock (time.time); the UI shows them relative to the first packet.
"""
import csv
import ctypes
import io
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Sequence

from asl_testing.events.types import MessageReceived, MessageSent
from asl_testing.services.monitor.signals import is_number, signal_paths

StreamKey = tuple[str, str, str, str]       # direction, message class, channel, signature (hex)


@dataclass
class Stream:
    key: StreamKey
    cls: type
    times: list[float] = field(default_factory=list)
    images: list[bytes] = field(default_factory=list)

    @property
    def id(self) -> str:
        return "|".join(self.key)


class Recorder:
    def __init__(self, projects: Sequence[type]):
        self.projects = list(projects)
        self.classes = _message_classes(projects)          # class name -> class
        self.streams: dict[StreamKey, Stream] = {}
        self._paths: dict[type, list] = {}                 # class -> [(path, getter)]
        self._lock = threading.Lock()                      # event thread appends, HTTP thread reads
        self.source = "empty"                              # "live", "csv: <name>" or "empty"

    # ---------------------------------------------------------------- input

    def on_event(self, event) -> None:
        """Handler for MessageReceived / MessageSent (runs in its subscriber thread)."""
        direction = "RX" if isinstance(event, MessageReceived) else "TX"
        msg = event.message
        sig = f"0x{msg._signature_id:X}" if msg._signature_id is not None else ""
        self._add((direction, type(msg).__name__, str(msg._channel), sig), type(msg),
                  event.host_time, event.image)

    def load_csv(self, text: str, name: str = "") -> int:
        """Adds the RX / TX rows of a CommLogger CSV; returns the number of packets loaded."""
        self.classes = _message_classes(self.projects)     # classes imported since the start count too
        count = 0
        for row in csv.DictReader(io.StringIO(text)):
            if row["direction"] not in ("RX", "TX"):
                continue                                   # invalid / unknown packets: no message
            cls = self.classes.get(row["message"])
            if cls is None:
                continue
            raw = bytes.fromhex(row["data"])
            t = datetime.fromisoformat(row["host_time"]).timestamp()
            self._add((row["direction"], row["message"], row["channel"], row["signature"]), cls,
                      t, _image(cls, raw))
            count += 1
        self.source = f"csv: {name}" if name else "csv"
        return count

    def clear(self) -> None:
        with self._lock:
            self.streams.clear()

    def _add(self, key: StreamKey, cls: type, t: float, image: bytes) -> None:
        with self._lock:
            stream = self.streams.get(key)
            if stream is None:
                stream = self.streams[key] = Stream(key, cls)
            stream.times.append(t)
            stream.images.append(image)

    # ---------------------------------------------------------------- output

    def t0(self) -> Optional[float]:
        with self._lock:
            starts = [s.times[0] for s in self.streams.values() if s.times]
        return min(starts) if starts else None

    def message_list(self) -> list[dict]:
        with self._lock:
            streams = list(self.streams.values())
        return [{"id": s.id, "direction": s.key[0], "name": s.key[1], "channel": s.key[2],
                 "signature": s.key[3], "count": len(s.times)} for s in streams]

    def fields(self, stream_id: str) -> list[dict]:
        """Every signal of a stream with its latest value."""
        stream = self._stream(stream_id)
        with self._lock:
            image = stream.images[-1] if stream.images else None
        msg = stream.cls.from_buffer_copy(image) if image else None
        out = []
        for path, get in self._signal_paths(stream.cls):
            value = _safe(get, msg) if msg is not None else None
            out.append({"path": path, "value": value, "plot": is_number(value)})
        return out

    def series(self, stream_id: str, path: str, since_index: int = 0) -> tuple[list, list, int]:
        """(times, values, next index) of one signal from since_index on."""
        stream = self._stream(stream_id)
        get = dict(self._signal_paths(stream.cls))[path]
        with self._lock:
            times = stream.times[since_index:]
            images = stream.images[since_index:]
        values = [_safe(get, stream.cls.from_buffer_copy(img)) for img in images]
        return times, values, since_index + len(times)

    def _stream(self, stream_id: str) -> Stream:
        with self._lock:
            for s in self.streams.values():
                if s.id == stream_id:
                    return s
        raise KeyError(stream_id)

    def _signal_paths(self, cls: type) -> list:
        if cls not in self._paths:
            self._paths[cls] = signal_paths(cls)
        return self._paths[cls]


def _message_classes(projects: Sequence[type]) -> dict[str, type]:
    """Every class below the projects, by name (the name CommLogger writes)."""
    found: dict[str, type] = {}
    todo = list(projects)
    while todo:
        cls = todo.pop()
        found.setdefault(cls.__name__, cls)
        todo.extend(cls.__subclasses__())
    return found


def _image(cls: type, raw: bytes) -> bytes:
    """ctypes layout of a message from its bytes on the wire (like decode, without validation).

    Fixed size: the wire equals the layout. Variable size: the body goes to the start, the
    checksum (last bytes of the packet) to the checksum field.
    """
    size = ctypes.sizeof(cls)
    if not getattr(cls, "_variable_size", False) or len(raw) >= size:
        return raw[:size].ljust(size, b"\0")
    probe = cls.from_buffer_copy(bytes(size))              # an unregistered object: only its layout is used
    offset, trailer = probe._trailer_offset(), probe._trailer_size()
    body = max(len(raw) - trailer, 0)
    image = bytearray(size)
    image[:body] = raw[:body]
    image[offset:offset + trailer] = raw[body:body + trailer]
    return bytes(image)


def _safe(get, msg) -> Any:
    try:
        value = get(msg)
    except Exception:
        return None
    return value if isinstance(value, (int, float, str)) else str(value)
