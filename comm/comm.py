"""Comm: the single entry point for test code.

Builds and connects the layers:  UtsClient -> Transport -> RxPoller / Dispatcher / TxScheduler -> EventBus.
Test code works with message objects and this class only.

    comm = Comm(FakeUtsClient(), [ProjectBase])
    comm.open()
    comm.send(req)                  # one-shot
    comm.start(cmd)                 # periodic, until comm.stop(cmd)
    comm.on_receive(status, handler)
    comm.close()
"""
import time
from typing import Callable, Iterable, Optional, Sequence

from comm.dispatcher import Dispatcher
from comm.rx import RxPoller
from comm.transport import RxFrame, Transport
from comm.tx import TxScheduler
from comm.uts import UtsClient
from events.bus import EventBus, Subscriber
from events.types import MessageReceived
from generic.basemessage import BaseMessageStructure
from generic.channel import Channel


class Comm:
    def __init__(self, uts: UtsClient, projects: Sequence[type[BaseMessageStructure]],
                 poll_interval: float = 0.01, channels: Iterable[Channel] = ()):
        self.bus = EventBus()
        self.transport = Transport(uts)
        self.dispatcher = Dispatcher(self.bus, projects)
        self.rx = RxPoller(self.transport, self.dispatcher, self.bus, projects, poll_interval, channels)
        self.tx = TxScheduler(self.transport, self.bus)

    # ---------------------------------------------------------------- life cycle

    def open(self) -> None:
        """Starts the RX poller and the TX scheduler threads."""
        self.rx.start()
        self.tx.start_thread()

    def close(self) -> None:
        """Stops periodic sending and polling, then the subscribers (after their queued events)."""
        self.tx.stop_thread()
        self.rx.stop()
        self.bus.close()

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
        """Starts sending a message with its tx period."""
        self.tx.start(msg)

    def stop(self, msg: BaseMessageStructure) -> None:
        """Stops the periodic sending of a message."""
        self.tx.stop(msg)

    # ---------------------------------------------------------------- RX

    def on_receive(self, msg: BaseMessageStructure, handler: Callable[[MessageReceived], None]) -> Subscriber:
        """Calls handler(event) in its own thread every time msg is received."""
        return self.bus.subscribe(MessageReceived, handler, where=msg)

    def wait_new(self, msg: BaseMessageStructure, timeout: float = 1.0, interval: float = 0.005) -> int:
        """Waits until msg has received a packet since its last has_new() call.

        Returns the number of new packets (cleared, as with has_new()), or 0 on timeout.
        Call msg.has_new() before sending a request, so an earlier packet is not taken as the answer.
        """
        deadline = time.monotonic() + timeout
        while True:
            new = msg.has_new()
            if new or time.monotonic() >= deadline:
                return new
            time.sleep(interval)

    def listen(self, channel: Channel) -> None:
        """Polls a channel even if no RX message is registered on it."""
        self.rx.listen(channel)

    @property
    def unknown(self) -> list[RxFrame]:
        """Received frames that matched no message (most recent last)."""
        return list(self.dispatcher.unknown)

    # ---------------------------------------------------------------- services

    def subscribe(self, event_type: type, handler: Callable, where: Optional[object] = None) -> Subscriber:
        """For services (logger, simulation, UI): subscribe to any event type; `object` = all."""
        return self.bus.subscribe(event_type, handler, where=where)
