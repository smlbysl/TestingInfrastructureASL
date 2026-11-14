"""TxScheduler: one-shot sends and one TX thread per channel for its periodic messages.

send(msg)      pack, envelope and backend request under the lock of the channel, so the TX thread and
               the test cannot mix up the counter; then after_send, WireSent and MessageSent.
               Sends on different channels do not wait for each other.
start / stop   add / remove a periodic message; the next time is due + period, so delays do not add up
A message that is no longer registered (replaced by a new object) is dropped from the table.
"""

__author__ = "İsmail Baysal"
import logging
import threading
import time
from typing import Optional

from asl_testing.backend.base import BackendError, Response
from asl_testing.runtime.transport import Transport
from asl_testing.events.bus import EventBus
from asl_testing.events.types import LinkError, MessageSent, WireSent
from asl_testing.message.base import BaseMessageStructure
from asl_testing.channel.channel import Channel


class ChannelTx:
    """Send lock, periodic table and TX thread of one channel."""

    def __init__(self, channel: Channel):
        self.channel = channel
        self.lock = threading.Lock()
        # id(msg) -> [msg, next due time (monotonic)]; ctypes objects are not hashable
        self.table: dict[int, list] = {}
        self.wake = threading.Event()
        self.thread: Optional[threading.Thread] = None


class TxScheduler:
    def __init__(self, transport: Transport, bus: EventBus, log=None):
        self.transport = transport
        self.bus = bus
        self.log = log or logging.getLogger(__name__)
        self._lines: dict[Channel, ChannelTx] = {}
        self._guard = threading.Lock()
        self._running = False
        self._stop = threading.Event()

    def _line(self, channel: Channel) -> ChannelTx:
        with self._guard:
            line = self._lines.get(channel)
            if line is None:
                line = self._lines[channel] = ChannelTx(channel)
            return line

    # ---------------------------------------------------------------- sending

    def send(self, msg: BaseMessageStructure) -> Response:
        """Sends a message once; the response is False in a condition if the request failed (LinkError is published)."""
        with self._line(msg._channel).lock:
            raw, image = msg._pack()
            try:
                wire, response = self.transport.send(msg._channel, raw)
                error = None if response.ok else BackendError(response)      # logged by the backend
            except Exception as failure:
                self.log.exception("send of %s failed on %s", type(msg).__name__, msg._channel)
                response, error = Response(ok=False, message=str(failure)), failure
            if error is not None:
                self.bus.publish(LinkError(msg._channel, "send", error, time.time()))
                return response
            msg._sent()
        self.log.debug("TX %s on %s (%d bytes)", type(msg).__name__, msg._channel, len(raw))
        now = time.time()
        self.bus.publish(WireSent(msg._channel, msg, wire, now))
        self.bus.publish(MessageSent(msg, raw, now, image, response.timestamp))
        return response

    # ---------------------------------------------------------------- periodic

    def start(self, msg: BaseMessageStructure) -> None:
        if msg._tx is None or not msg._tx.timing.is_periodic:
            raise ValueError(f"{type(msg).__name__} has no periodic TX timing (tx=Timing(period))")
        line = self._line(msg._channel)
        line.table[id(msg)] = [msg, time.monotonic()]
        self.log.info("periodic TX started: %s every %s s", type(msg).__name__, msg._tx.timing.period)
        self._start_line(line)
        line.wake.set()

    def stop(self, msg: BaseMessageStructure) -> None:
        line = self._line(msg._channel)
        if line.table.pop(id(msg), None) is not None:
            self.log.info("periodic TX stopped: %s", type(msg).__name__)
        line.wake.set()

    def is_running(self, msg: BaseMessageStructure) -> bool:
        return id(msg) in self._line(msg._channel).table

    def tick(self, line: ChannelTx) -> Optional[float]:
        """Sends what is due on a channel; returns seconds to its next due message, None if there is none."""
        now = time.monotonic()
        for key, entry in list(line.table.items()):
            msg, due = entry
            if not msg._registered:
                line.table.pop(key, None)
                continue
            if due <= now:
                self.send(msg)
                entry[1] = due + msg._tx.timing.period
        if not line.table:
            return None
        return max(0.0, min(due for _, due in list(line.table.values())) - time.monotonic())

    # ---------------------------------------------------------------- threads

    def start_thread(self) -> None:
        """Starts the TX thread of every channel that has periodic messages; later ones start with start(msg)."""
        self._stop.clear()
        self._running = True
        with self._guard:
            lines = list(self._lines.values())
        for line in lines:
            if line.table:
                self._start_line(line)

    def stop_thread(self) -> None:
        self._running = False
        self._stop.set()
        with self._guard:
            lines = list(self._lines.values())
        for line in lines:
            line.wake.set()
        for line in lines:
            if line.thread is not None:
                line.thread.join()
                line.thread = None

    def _start_line(self, line: ChannelTx) -> None:
        with self._guard:
            if not self._running or line.thread is not None:
                return
            line.thread = threading.Thread(target=self._run, args=(line,), name=f"Tx-{line.channel}", daemon=True)
        line.thread.start()

    def _run(self, line: ChannelTx) -> None:
        while not self._stop.is_set():
            wait = self.tick(line)
            line.wake.wait(wait)
            line.wake.clear()
