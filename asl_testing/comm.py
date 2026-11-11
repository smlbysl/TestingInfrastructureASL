"""Comm: the entry point for test code; builds and connects the layers.

    UtsClient -> Transport -> RxPoller / Dispatcher / TxScheduler -> EventBus

    comm = Comm(FakeUtsClient(), [ProjectBase])
    comm.open()
    comm.send(req)                                  # once
    comm.start(cmd)                                 # periodic, until comm.stop(cmd)
    comm.wait_for(status, lambda s: s.speed == 10)
    comm.control.add_filter(status)                 # UTS config and filters
    comm.close()

Every part logs on its own logger (asl_testing.*). Comm(..., logger=x) sends all of it to x.
"""

__author__ = "İsmail Baysal"
import logging
import time
from typing import Callable, Iterable, Optional, Sequence

from asl_testing.runtime.dispatcher import Dispatcher
from asl_testing.runtime.rx import RxPoller
from asl_testing.runtime.transport import RxFrame, Transport
from asl_testing.runtime.tx import TxScheduler
from asl_testing.uts.client import UtsClient
from asl_testing.uts.control import UtsControl
from asl_testing.events.bus import EventBus, Subscriber
from asl_testing.events.types import MessageReceived
from asl_testing.message.base import BaseMessageStructure
from asl_testing.message.history import Record
from asl_testing.channel.channel import Channel


def _wait(check: Callable[[], int], timeout: float, interval: float) -> int:
    """Calls check() until it returns non-zero or the timeout passes."""
    deadline = time.monotonic() + timeout
    while True:
        new = check()
        if new or time.monotonic() >= deadline:
            return new
        time.sleep(interval)


class Comm:
    def __init__(self, uts: UtsClient, projects: Sequence[type[BaseMessageStructure]],
                 poll_interval: float = 0.01, channels: Iterable[Channel] = (), logger=None,
                 protocols: Optional[dict] = None):
        """protocols: ProtocolType -> Protocol, replaces the default protocol objects."""
        self.log = logger or logging.getLogger(__name__)
        self.bus = EventBus(log=logger)
        self.transport = Transport(uts, protocols)
        self.dispatcher = Dispatcher(self.bus, projects, log=logger)
        self.rx = RxPoller(self.transport, self.dispatcher, self.bus, projects, poll_interval, channels, log=logger)
        self.tx = TxScheduler(self.transport, self.bus, log=logger)
        self.control = UtsControl(uts, log=logger)

    # ---------------------------------------------------------------- life cycle

    def open(self) -> None:
        """Starts the RX and TX threads."""
        self.rx.start()
        self.tx.start_thread()
        self.log.info("comm opened")

    def close(self) -> None:
        """Stops TX, RX and the subscribers (after their queued events)."""
        self.tx.stop_thread()
        self.rx.stop()
        self.bus.close()
        self.log.info("comm closed")

    def __enter__(self) -> "Comm":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------------------------------------------------------------- TX

    def send(self, msg: BaseMessageStructure) -> bool:
        """Sends a message once."""
        return self.tx.send(msg)

    def start(self, msg: BaseMessageStructure) -> None:
        """Starts sending a message every tx period."""
        self.tx.start(msg)

    def stop(self, msg: BaseMessageStructure) -> None:
        """Stops the periodic sending of a message."""
        self.tx.stop(msg)

    # ---------------------------------------------------------------- RX

    def on_receive(self, msg: BaseMessageStructure, handler: Callable[[MessageReceived], None]) -> Subscriber:
        """Calls handler(event) in its own thread for every valid packet of msg."""
        return self.bus.subscribe(MessageReceived, handler, where=msg)

    def wait_new(self, msg: BaseMessageStructure, timeout: float = 1.0, interval: float = 0.005) -> int:
        """Waits for a packet of msg since its last has_new(); returns the count (cleared) or 0.

        Call msg.has_new() before the request, so an earlier packet is not taken as the answer.
        """
        return _wait(msg.has_new, timeout, interval)

    def wait_for(self, msg: BaseMessageStructure, predicate: Callable[[BaseMessageStructure], bool],
                 timeout: float = 1.0, after: Optional[int] = None) -> Optional[Record]:
        """Waits for a packet of msg whose values satisfy predicate; returns its Record or None.

        Every packet is checked, also one overwritten by a later packet of the same poll.
        after: a mark from msg.rx_history.mark(); default: from now on.

            mark = status.rx_history.mark()
            comm.send(request)
            rec = comm.wait_for(status, lambda s: s.speed == 10, timeout=1.0, after=mark)
        """
        history = msg.rx_history
        if history is None:
            raise ValueError(f"{type(msg).__name__} is not received (no RX direction), nothing to wait for")
        start = history.mark() if after is None else after
        return history.wait_for(predicate, start, timeout)

    def wait_sent(self, msg: BaseMessageStructure, timeout: float = 1.0, interval: float = 0.005) -> int:
        """Waits for a successful send of msg since its last has_sent(); returns the count (cleared) or 0."""
        return _wait(msg.has_sent, timeout, interval)

    def listen(self, channel: Channel) -> None:
        """Polls a channel even if no RX message is registered on it."""
        self.rx.listen(channel)

    @property
    def unknown(self) -> list[RxFrame]:
        """Frames that matched no message, oldest first."""
        return list(self.dispatcher.unknown)

    # ---------------------------------------------------------------- services

    def subscribe(self, event_type: type, handler: Callable, where: Optional[object] = None) -> Subscriber:
        """Subscribes to an event type; `object` subscribes to all events."""
        return self.bus.subscribe(event_type, handler, where=where)
