"""RxPoller: one thread that polls UTS at a fixed interval.

Each cycle:
1. reads every channel that has RX messages or was added with listen()
2. publishes WireReceived for each packet and passes it to the dispatcher
3. checks periodic RX messages for timeout on the UTS clock (RxTimeout / RxRestored)

A failed poll gives LinkError; a packet that fails in the dispatcher is logged and skipped.
Polling goes on in both cases.
"""

__author__ = "İsmail Baysal"
import logging
import threading
import time
from typing import Iterable, Optional, Sequence

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
        self._thread: Optional[threading.Thread] = None

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
        for channel in sorted(self.channels(), key=lambda ch: ch.key):     # fixed order every cycle
            try:
                frames = self.transport.poll(channel)
            except Exception as error:
                self.log.exception("UTS poll failed on %s", channel)
                self.bus.publish(LinkError(channel, "poll", error, time.time()))
                continue
            for frame in frames:
                self.clock.update(frame.timestamp)
                self.bus.publish(WireReceived(frame.channel, frame.wire, frame.timestamp, frame.host_time))
                try:
                    self.dispatcher.dispatch(frame)
                except Exception:
                    self.log.exception("RX of a %d byte packet on %s failed", len(frame.data), channel)
        self._check_timeouts()

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

    # ---------------------------------------------------------------- thread

    def start(self) -> None:
        self._started = time.monotonic()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="RxPoller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.poll_once()
