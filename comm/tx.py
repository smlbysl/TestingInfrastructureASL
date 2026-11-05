"""TxScheduler: one-shot sends and one thread for all periodic messages.

- send(msg): counter, checksum, bytes, raw rules, envelope and the UTS request happen under one lock,
  so the scheduler and the test sending the same message at the same time cannot mix up the counter.
- start(msg) / stop(msg): adds / removes a periodic message. The next send time is advanced by
  the period (not now + period), so the delay does not accumulate.
- A message that is no longer registered (replaced by a new object) is dropped from the table.
"""
import logging
import threading
import time
from typing import Optional

from comm.transport import Transport
from events.bus import EventBus
from events.types import LinkError, MessageSent
from generic.basemessage import BaseMessageStructure

log = logging.getLogger(__name__)


class TxScheduler:
    def __init__(self, transport: Transport, bus: EventBus):
        self.transport = transport
        self.bus = bus
        self.lock = threading.Lock()                # held while a message is packed and sent
        # id(message) -> [message, next due (monotonic)]; ctypes objects are not hashable
        self._table: dict[int, list] = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---------------------------------------------------------------- sending

    def send(self, msg: BaseMessageStructure) -> bool:
        """Sends a message once. Returns False if the UTS request failed (logged, LinkError published)."""
        with self.lock:
            raw = msg.pack()
            image = bytes(msg)
            try:
                wire = self.transport.send(msg._channel, raw)
            except Exception as error:
                log.error("send %s on %s failed: %s", type(msg).__name__, msg._channel, error)
                self.bus.publish(LinkError(msg._channel.link, "send", error, time.time()))
                return False
        self.bus.publish(MessageSent(msg, raw, wire, time.time(), image))
        return True

    # ---------------------------------------------------------------- periodic

    def start(self, msg: BaseMessageStructure) -> None:
        if msg._tx is None or not msg._tx.timing.is_periodic:
            raise ValueError(f"{type(msg).__name__} has no periodic TX timing (tx=Timing(period))")
        self._table[id(msg)] = [msg, time.monotonic()]
        log.info("periodic %s on %s started (%s s)", type(msg).__name__, msg._channel, msg._tx.timing.period)
        self._wake.set()

    def stop(self, msg: BaseMessageStructure) -> None:
        if self._table.pop(id(msg), None) is not None:
            log.info("periodic %s on %s stopped", type(msg).__name__, msg._channel)
        self._wake.set()

    def is_running(self, msg: BaseMessageStructure) -> bool:
        return id(msg) in self._table

    def running(self) -> list[BaseMessageStructure]:
        return [msg for msg, _ in list(self._table.values())]

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
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            wait = self.tick()
            self._wake.wait(wait)
            self._wake.clear()
