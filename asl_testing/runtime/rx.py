"""RxPoller: one RX thread per channel and one watchdog thread.

RX thread of a channel, every interval:
1. reads what the channel's interface received
2. publishes WireReceived for each packet and passes it to the dispatcher

Watchdog, every interval:
1. starts the RX thread of a channel that has RX messages or was added with listen()
2. checks periodic RX messages for timeout on the UTS clock (RxTimeout / RxRestored)

A channel whose request hangs or fails does not hold up the other channels or the timeout check.
A failed poll gives LinkError; a packet that fails in the dispatcher is logged and skipped.
Polling goes on in both cases. The RX thread of a channel that is no longer needed ends.
"""

__author__ = "İsmail Baysal"
import logging
import threading
import time
from typing import Iterable, Optional, Sequence

from asl_testing.backend.base import BackendError
from asl_testing.runtime.clock import UtsClock
from asl_testing.runtime.dispatcher import Dispatcher
from asl_testing.runtime.transport import Transport
from asl_testing.events.bus import EventBus
from asl_testing.events.types import LinkError, RxRestored, RxTimeout, WireReceived
from asl_testing.message.base import BaseMessageStructure
from asl_testing.channel.channel import Channel


class RxPoller:
    def __init__(self, transport: Transport, dispatcher: Dispatcher, bus: EventBus,
                 projects: Sequence[type[BaseMessageStructure]], interval: float,
                 channels: Iterable[Channel] = (), log=None):
        self.transport = transport
        self.dispatcher = dispatcher
        self.bus = bus
        self.projects = projects
        self.log = log or logging.getLogger(__name__)
        self.interval = interval                    # seconds between two cycles
        self.clock = UtsClock()
        self._extra = set(channels)                 # polled even without RX messages
        self._late: set[int] = set()                # id() of late messages; ctypes objects are not hashable
        self._started: Optional[float] = None
        self._stop = threading.Event()
        self._watchdog: Optional[threading.Thread] = None
        self._threads: dict[Channel, threading.Thread] = {}       # RX thread of each polled channel
        self._guard = threading.Lock()

    def listen(self, channel: Channel) -> None:
        """Polls a channel that has no RX message (to see its packets as unknown)."""
        self._extra.add(channel)
        self.log.info("listening on %s", channel)

    def channels(self) -> set[Channel]:
        found = set(self._extra)
        for project in self.projects:
            for reg in project.families():
                found |= reg.channels
        return found

    def poll_once(self) -> None:
        """Polls every channel once in the calling thread, then checks the timeouts (for tests without threads)."""
        for channel in sorted(self.channels(), key=lambda ch: ch.key):
            self.poll_channel(channel)
        self._check_timeouts()

    def poll_channel(self, channel: Channel) -> None:
        try:
            frames = self.transport.poll(channel)
        except Exception as error:
            if not isinstance(error, BackendError):                     # a failed request is logged by the backend
                self.log.exception("poll failed on %s", channel)
            self.bus.publish(LinkError(channel, "poll", error, time.time()))
            return
        for frame in frames:
            self.clock.update(frame.timestamp)
            self.bus.publish(WireReceived(frame.channel, frame.wire, frame.timestamp, frame.host_time))
            try:
                self.dispatcher.dispatch(frame)
            except Exception:
                self.log.exception("RX of a %d byte packet on %s failed", len(frame.data), channel)

    # ---------------------------------------------------------------- timeouts

    def _check_timeouts(self) -> None:
        for project in self.projects:
            for reg in project.families():
                for msg in list(reg.periodic_rx):
                    self._check(msg)

    def _check(self, msg: BaseMessageStructure) -> None:
        rx = msg._rx
        limit = rx.timing.period * rx.timing.tolerance
        age = self._age(rx)
        late = id(msg) in self._late
        if age > limit and not late:
            self._late.add(id(msg))
            self.log.warning("%s on %s not received for %.3f s (period %s s)", type(msg).__name__,
                             msg._channel, age, rx.timing.period)
            self.bus.publish(RxTimeout(msg, age, time.time()))
        elif age <= limit and late:
            self._late.discard(id(msg))
            self.log.info("%s on %s received again", type(msg).__name__, msg._channel)
            self.bus.publish(RxRestored(msg, time.time()))

    def _age(self, rx) -> float:
        """Age of the last packet on the UTS clock (host clock until a UTS time is known)."""
        now = self.clock.now()
        if rx.timestamp is not None and now is not None:
            return now - rx.timestamp
        # Never received: count from the later of poll start and object creation.
        since = rx.last_time if rx.last_time is not None else max(self._started, rx.created)
        return time.monotonic() - since

    # ---------------------------------------------------------------- threads

    def start(self) -> None:
        self._started = time.monotonic()
        self._stop.clear()
        self._watchdog = threading.Thread(target=self._watch, name="RxWatchdog", daemon=True)
        self._watchdog.start()

    def stop(self) -> None:
        self._stop.set()
        if self._watchdog is not None:
            self._watchdog.join()
        with self._guard:
            threads = list(self._threads.values())
        for thread in threads:
            thread.join()

    def _watch(self) -> None:
        while not self._stop.wait(self.interval):
            self._start_channels()
            self._check_timeouts()

    def _start_channels(self) -> None:
        for channel in self.channels():
            with self._guard:
                if channel in self._threads:
                    continue
                thread = threading.Thread(target=self._run, args=(channel,), name=f"Rx-{channel}", daemon=True)
                self._threads[channel] = thread
            thread.start()

    def _run(self, channel: Channel) -> None:
        while not self._stop.is_set() and channel in self.channels():
            self.poll_channel(channel)
            self._stop.wait(self.interval)
        with self._guard:
            del self._threads[channel]
