"""RxPoller: one thread that polls every UTS link at a fixed interval.

Every cycle:
1. polls each link of the setup and hands every frame to the dispatcher
2. checks periodic RX messages for timeouts on the UTS clock and publishes RxTimeout / RxRestored
A failed poll is logged and published as LinkError; polling continues.
"""
import logging
import threading
import time
from typing import Optional, Sequence

from comm.clock import UtsClock
from comm.dispatcher import Dispatcher
from comm.link import Link
from comm.transport import Transport
from events.bus import EventBus
from events.types import BufferOverflow, LinkError, RxRestored, RxTimeout
from generic.basemessage import BaseMessageStructure

log = logging.getLogger(__name__)


class RxPoller:
    def __init__(self, transport: Transport, dispatcher: Dispatcher, bus: EventBus,
                 projects: Sequence[type[BaseMessageStructure]], links: Sequence[Link], interval: float):
        self.transport = transport
        self.dispatcher = dispatcher
        self.bus = bus
        self.projects = projects
        self.links = links
        self.interval = interval                    # seconds between two poll cycles
        self.clock = UtsClock()
        self._late: set[int] = set()                # id() of timed-out messages (ctypes objects are not hashable)
        self._started: Optional[float] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def poll_once(self) -> None:
        for link in self.links:
            try:
                result = self.transport.poll(link)
            except Exception as error:
                log.error("poll %s failed: %s", link, error)
                self.bus.publish(LinkError(link, "poll", error, time.time()))
                continue
            if result.overflow:
                log.warning("%s: UTS receive buffer overflowed, packets were lost", link)
                self.bus.publish(BufferOverflow(link, time.time()))
            for frame in result.frames:
                self.clock.update(frame.timestamp)
                self.dispatcher.dispatch(frame)
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
            log.warning("%s on %s not received for %.3f s (period %s s)",
                        type(msg).__name__, msg._channel, age, rx.timing.period)
            self.bus.publish(RxTimeout(msg, age, time.time()))
        elif age <= limit and late:
            self._late.discard(id(msg))
            log.info("%s on %s received again", type(msg).__name__, msg._channel)
            self.bus.publish(RxRestored(msg, time.time()))

    def _age(self, rx) -> float:
        """Age of the last packet on the UTS clock; on the host clock until UTS time is known."""
        now = self.clock.now()
        if rx.timestamp is not None and now is not None:
            return now - rx.timestamp
        # Never arrived: count from when polling started or the object was created, whichever is later
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
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.poll_once()
