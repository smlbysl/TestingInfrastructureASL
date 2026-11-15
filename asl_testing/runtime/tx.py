"""TxScheduler: one-shot sends and one thread for all periodic messages.

send(msg)      pack, envelope, UTS request and after_send under the lock of the message, so the scheduler
               and the test cannot mix up its counter; then WireSent and MessageSent.
               Different messages do not wait for each other; the UTS client sends one POST at a time
               per interface. Lock order: message -> interface.
start / stop   add / remove a periodic message; the next time is due + period, so delays do not add up
A message that is no longer registered (replaced by a new object) is dropped from the table.
"""

__author__ = "İsmail Baysal"
import logging
import threading
import time
from typing import Optional

from asl_testing.runtime.transport import Transport
from asl_testing.events.bus import EventBus
from asl_testing.events.types import LinkError, MessageSent, WireSent
from asl_testing.message.base import BaseMessageStructure
from asl_testing.channel.channel import Channel


class TxScheduler:
    def __init__(self, transport: Transport, bus: EventBus, log=None):
        self.transport = transport
        self.bus = bus
        self.log = log or logging.getLogger(__name__)
        # id(msg) -> [msg, next due time (monotonic)]; ctypes objects are not hashable
        self._table: dict[int, list] = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---------------------------------------------------------------- sending

    def send(self, msg: BaseMessageStructure) -> bool:
        """Sends a message once; False if the UTS request failed (LinkError is published)."""
        with msg._lock:
            raw, image = msg._pack()
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

    def running(self, channel: Optional[Channel] = None) -> list[BaseMessageStructure]:
        """Messages sent periodically now; with a channel, only those on it."""
        return [msg for msg, _ in list(self._table.values()) if channel is None or msg._channel is channel]

    def tick(self) -> Optional[float]:
        """Sends what is due; returns seconds to the next due message, None if there is none."""
        now = time.monotonic()
        for key, entry in list(self._table.items()):
            msg, due = entry
            if not msg._registered:
                self._table.pop(key, None)
                continue
            if due <= now:
                self.send(msg)
                entry[1] = due + msg._tx.timing.period
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
