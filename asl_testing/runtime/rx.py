"""RxPoller: one thread that polls UTS at a fixed interval.

Every cycle:
1. polls each RX address once: the addresses of channels with registered RX messages
   and of channels added with listen(); channels sharing an address are told apart by their envelope
2. publishes WireReceived for every packet and hands it to the dispatcher
3. checks periodic RX messages for timeouts on the UTS clock and publishes RxTimeout / RxRestored
A failed poll is published as LinkError, logged as ERROR (with traceback) and polling continues.
An exception while dispatching one packet is logged as ERROR and the next packet is handled.
Timeouts are logged as WARNING, recoveries as INFO.
"""
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
from asl_testing.channel.channel import Address, Channel, by_address


class RxPoller:
    def __init__(self, transport: Transport, dispatcher: Dispatcher, bus: EventBus,
                 projects: Sequence[type[BaseMessageStructure]], interval: float,
                 channels: Iterable[Channel] = (), log=None):
        self.transport = transport
        self.dispatcher = dispatcher
        self.bus = bus
        self.projects = projects
        self.log = log or logging.getLogger(__name__)
        self.interval = interval                    # seconds between two poll cycles
        self.clock = UtsClock()
        self._extra = set(channels)                 # channels polled even without RX messages
        self._late: set[int] = set()                # id() of timed-out messages (ctypes objects are not hashable)
        self._started: Optional[float] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def listen(self, channel: Channel) -> None:
        """Also polls a channel that has no registered RX message (to see unknown packets)."""
        self._extra.add(channel)
        self.log.info("listening on %s", channel)

    def channels(self) -> set[Channel]:
        found = set(self._extra)
        for project in self.projects:
            for reg in project.families():
                found |= reg.channels
        return found

    def addresses(self) -> dict[Address, list[Channel]]:
        """Address -> its channels, in the order they are tried on RX."""
        return by_address(self.channels())

    def poll_once(self) -> None:
        for address, channels in self.addresses().items():
            try:
                frames = self.transport.poll(address, channels)
            except Exception as error:
                self.log.exception("UTS poll failed on %s", address)
                self.bus.publish(LinkError(channels[0], "poll", error, time.time()))
                continue
            for frame in frames:
                self.clock.update(frame.timestamp)
                self.bus.publish(WireReceived(frame.channel, frame.protocol, frame.interface, frame.wire,
                                              frame.timestamp, frame.host_time))
                try:
                    self.dispatcher.dispatch(frame)
                except Exception:                   # one bad packet must not stop the receiver
                    self.log.exception("RX of a %d byte packet on %s failed", len(frame.data), address)
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

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.poll_once()
