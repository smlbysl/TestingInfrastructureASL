"""TxScheduler: one-shot sends and one thread for all periodic messages.

- send(msg): counter, checksum, bytes, envelope and the UTS request happen under one lock, so the
  scheduler and the test sending the same message at the same time cannot mix up the counter.
  Publishes WireSent (bytes on the line) and MessageSent. After a successful send the after_send
  hooks of the special fields run (still under the lock); the events carry the values that were sent.
- start(msg) / stop(msg): adds / removes a periodic message. The next send time is advanced by
  the period (not now + period), so the delay does not accumulate.
- A message that is no longer registered (replaced by a new object) is dropped from the table.
Logs: a failed send as ERROR (with traceback), periodic start / stop as INFO, every send as DEBUG.
"""
import logging
import threading
import time
from typing import Optional

from asl_testing.runtime.transport import Transport
from asl_testing.events.bus import EventBus
from asl_testing.events.types import LinkError, MessageSent, WireSent
from asl_testing.message.base import BaseMessageStructure


class TxScheduler:
    def __init__(self, transport: Transport, bus: EventBus, log=None):
        self.transport = transport
        self.bus = bus
        self.log = log or logging.getLogger(__name__)
        self._send_lock = threading.Lock()
        # id(message) -> [message, next due (monotonic)]; ctypes objects are not hashable
        self._table: dict[int, list] = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---------------------------------------------------------------- sending

    def send(self, msg: BaseMessageStructure) -> bool:
        """Sends a message once. Returns False if the UTS request failed (LinkError is published)."""
        with self._send_lock:
            raw = msg.pack()
            image = bytes(msg)
            try:
                wire = self.transport.send(msg._channel, raw)
            except Exception as error:
                self.log.exception("UTS send of %s failed on %s", type(msg).__name__, msg._channel)
                self.bus.publish(LinkError(msg._channel, "send", error, time.time()))
                return False
            msg._sent()
        self.log.debug("TX %s on %s (%d bytes)", type(msg).__name__, msg._channel, len(raw))
        now = time.time()
        self.bus.publish(WireSent(msg._channel, msg, wire, now))
        self.bus.publish(MessageSent(msg, raw, now, image))
        return True

    # ---------------------------------------------------------------- periodic

    def start(self, msg: BaseMessageStructure) -> None:
        if msg._tx is None or not msg._tx.timing.is_periodic:
            raise ValueError(f"{type(msg).__name__} has no periodic TX timing (tx=Timing(period))")
        self._table[id(msg)] = [msg, time.monotonic()]
        self.log.info("periodic TX started: %s every %s s", type(msg).__name__, msg._tx.timing.period)
        self._wake.set()

    def stop(self, msg: BaseMessageStructure) -> None:
        if self._table.pop(id(msg), None) is not None:
            self.log.info("periodic TX stopped: %s", type(msg).__name__)
        self._wake.set()

    def is_running(self, msg: BaseMessageStructure) -> bool:
        return id(msg) in self._table

    def tick(self) -> Optional[float]:
        """Sends what is due; returns seconds until the next due message (None if the table is empty)."""
        now = time.monotonic()
        for key, entry in list(self._table.items()):
            msg, due = entry
            if not msg._registered:
                self._table.pop(key, None)
                continue
            if due <= now:
                self.send(msg)
                entry[1] = due + msg._tx.timing.period   # harmless if stop() removed the entry meanwhile
        if not self._table:
            return None
        return max(0.0, min(due for _, due in list(self._table.values())) - time.monotonic())

    # ---------------------------------------------------------------- thread

    def start_thread(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="TxScheduler", daemon=True)
        self._thread.start()

    def stop_thread(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join()

    def _run(self) -> None:
        while not self._stop.is_set():
            wait = self.tick()
            self._wake.wait(wait)
            self._wake.clear()
