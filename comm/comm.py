"""Comm: the single entry point for test code.

    comm = Comm.load("setups/fake.toml", ProjectBase, MyChannels)
    with comm:                              # open(): configure UTS, start the threads
        comm.send(req)                      # one-shot
        comm.start(cmd) / comm.stop(cmd)    # periodic
        comm.on_receive(status, handler)    # listener in its own thread
        comm.reset()                        # back to the baseline, e.g. after every test

Layers built and connected here:
    UtsClient -> Transport -> RxPoller / Dispatcher / TxScheduler -> EventBus -> services, listeners
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence, Union

from comm.dispatcher import Dispatcher
from comm.link import Link
from comm.rx import RxPoller
from comm.transport import RxFrame, Transport
from comm.tx import TxScheduler
from comm.uts.base import FilterGroups, UtsClient, UtsError
from events.bus import EventBus, Subscriber
from events.types import LinkError, MessageReceived
from generic.basemessage import BaseMessageStructure
from generic.channel import Channel, ChannelSet

log = logging.getLogger(__name__)

Target = Union[Channel, Link, str]              # a channel, a link or a link name


@dataclass
class _Baseline:
    periodic: dict[int, BaseMessageStructure] = field(default_factory=dict)
    subscribers: set[int] = field(default_factory=set)
    # id(msg) -> (msg, image, number of on_send callouts, number of on_receive callouts)
    messages: dict[int, tuple] = field(default_factory=dict)
    # id(channel) -> (number of rx rules, number of tx rules)
    rules: dict[int, tuple[int, int]] = field(default_factory=dict)


class Comm:
    def __init__(self, uts: UtsClient, projects: Union[type, Sequence[type]], links: dict[str, Link],
                 channels: type[ChannelSet], poll_interval: float = 0.01):
        self.uts = uts
        self.projects = list(projects) if isinstance(projects, (list, tuple)) else [projects]
        self.links = links
        self.channels = channels
        self.bus = EventBus()
        self.transport = Transport(uts, channels)
        self.dispatcher = Dispatcher(self.bus, self.projects)
        self.rx = RxPoller(self.transport, self.dispatcher, self.bus, self.projects,
                           list(links.values()), poll_interval)
        self.tx = TxScheduler(self.transport, self.bus)
        self.config: Any = None                 # set by Comm.load
        self.run_dir = None
        self.log_file = None
        self._services: list = []
        self._baseline = _Baseline()
        self._open = False

    @classmethod
    def load(cls, setup_file, projects, channels: type[ChannelSet]) -> "Comm":
        """Builds a Comm from a setup file (links, UTS, logging). See comm.bootstrap."""
        from comm.bootstrap import build
        return build(setup_file, projects if isinstance(projects, (list, tuple)) else [projects], channels)

    def add_service(self, service) -> None:
        """A service is closed (service.close()) when Comm closes."""
        self._services.append(service)

    # ---------------------------------------------------------------- life cycle

    def open(self) -> None:
        """Configures UTS (or reads its settings), starts the threads and marks the baseline."""
        for link in self.links.values():
            self._prepare(link)
        self.rx.start()
        self.tx.start_thread()
        self._open = True
        self.mark_baseline()
        log.info("comm open")

    def close(self) -> None:
        """Stops periodic sending and polling, then the subscribers (after their queued events)."""
        if not self._open:
            return
        self.tx.stop_thread()
        self.rx.stop()
        self.bus.close()
        for service in self._services:
            service.close()
        self._open = False
        log.info("comm closed")

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

    def is_running(self, msg: BaseMessageStructure) -> bool:
        return self.tx.is_running(msg)

    # ---------------------------------------------------------------- RX

    def on_receive(self, msg: BaseMessageStructure, handler: Callable[[MessageReceived], None]) -> Subscriber:
        """Calls handler(event) in its own thread every time msg is received."""
        return self.bus.subscribe(MessageReceived, handler, where=msg)

    def subscribe(self, event_type: type, handler: Callable, where: Optional[object] = None) -> Subscriber:
        """For services (simulation, UI ...): any event type; `object` = all events."""
        return self.bus.subscribe(event_type, handler, where=where)

    @property
    def unknown(self) -> list[RxFrame]:
        """Received frames that matched no message (most recent last)."""
        return list(self.dispatcher.unknown)

    # ---------------------------------------------------------------- UTS functions

    def clear(self, target: Target) -> None:
        """Empties the UTS receive buffer of a link and any partial packet kept by its splitter."""
        link = self._link(target)
        self.uts.clear(link)
        link.splitter.reset()
        log.info("%s: receive buffer cleared", link)

    def set_filter(self, target: Target, groups: FilterGroups, kind: str = "INCLUSIVE") -> None:
        """UTS receive filter: OR of groups, each an AND of (byte position on the line, value)."""
        link = self._link(target)
        self.uts.write_filter(link, kind, groups)
        log.info("%s: filter %s %s", link, kind, groups)

    def clear_filter(self, target: Target) -> None:
        link = self._link(target)
        self.uts.write_filter(link, "NONE", [])
        log.info("%s: filter cleared", link)

    def configure(self, target: Target, **settings) -> None:
        """Changes settings of a link and writes them to UTS (also for a manual link)."""
        link = self._link(target)
        for name, value in settings.items():
            if name not in link.uts_keys():
                raise ValueError(f"{link}: unknown setting '{name}'")
            setattr(link, name, value)
            link.given.add(name)
        self.uts.write_config(link)
        self._read_back(link)
        log.info("%s configured: %s", link, settings)

    # ---------------------------------------------------------------- baseline / reset

    def mark_baseline(self) -> None:
        """Saves the current state as the baseline that reset() returns to.

        Called by open(); call it again after setting up what must run during every test
        (e.g. a heartbeat started with comm.start, callouts that always apply).
        """
        b = _Baseline()
        b.periodic = {id(m): m for m in self.tx.running()}
        b.subscribers = {id(s) for s in self.bus.subscribers()}
        for msg in self._messages():
            b.messages[id(msg)] = (msg, bytes(msg), len(msg._on_send), len(msg._on_receive))
        for ch in self.channels.all():
            b.rules[id(ch)] = (len(ch._rx_rules), len(ch._tx_rules))
        self._baseline = b
        log.debug("baseline: %d periodic, %d subscribers, %d messages",
                  len(b.periodic), len(b.subscribers), len(b.messages))

    def reset(self, clear_buffers: bool = False) -> None:
        """Undoes what happened since the baseline: e.g. after every test.

        - periodic messages started since then stop; baseline ones run again
        - listeners, callouts and raw rules added since then are removed
        - message fields go back to their baseline values (counters keep counting)
        - RX/TX counts and the unknown list are cleared
        - clear_buffers=True also empties the UTS receive buffers
        """
        b = self._baseline
        for msg in self.tx.running():
            if id(msg) not in b.periodic:
                self.tx.stop(msg)
        for msg in b.periodic.values():
            if msg._registered and not self.tx.is_running(msg):
                self.tx.start(msg)

        for sub in self.bus.subscribers():
            if id(sub) not in b.subscribers:
                self.bus.unsubscribe(sub)

        with self.tx.lock:                      # no message is packed while its fields are restored
            for msg in self._messages():
                saved = b.messages.get(id(msg))
                if saved is None or saved[0] is not msg:
                    del msg._on_send[:], msg._on_receive[:]
                else:
                    _, image, n_send, n_receive = saved
                    del msg._on_send[n_send:], msg._on_receive[n_receive:]
                    msg.restore(image)
                if msg._rx is not None:
                    msg._rx.reset_counts()
                if msg._tx is not None:
                    msg._tx.reset_counts()

        for ch in self.channels.all():
            n_rx, n_tx = b.rules.get(id(ch), (0, 0))
            del ch._rx_rules[n_rx:], ch._tx_rules[n_tx:]

        self.dispatcher.unknown.clear()
        if clear_buffers:
            for link in self.links.values():
                self.clear(link)
        log.debug("reset to baseline")

    # ---------------------------------------------------------------- helpers

    def _prepare(self, link: Link) -> None:
        """auto: write the setup settings to UTS; manual: keep the UTS settings. Then read them back."""
        try:
            if link.config_mode == "auto":
                self.uts.write_config(link)
            self._read_back(link)
        except Exception as error:
            self.bus.publish(LinkError(link, "configure", error, time.time()))
            raise UtsError(f"{link}: configuration failed: {error}") from error

    def _read_back(self, link: Link) -> None:
        config, status = self.uts.read_config(link)
        for difference in link.apply_uts(config):
            if link.config_mode == "manual":
                log.warning("%s %s (manual: UTS value used)", link, difference)
            else:
                log.warning("%s %s (UTS did not take the setup value)", link, difference)
        if status.get("isOpen") is False:
            raise UtsError(f"{link}: UTS reports the interface is not open ({status.get('lastError')})")
        log.info("%s %s: %s", link, link.config_mode, config)

    def _link(self, target: Target) -> Link:
        if isinstance(target, Channel):
            return target.link
        if isinstance(target, Link):
            return target
        return self.links[target]

    def _messages(self) -> list[BaseMessageStructure]:
        return [msg for project in self.projects for reg in project.families() for msg in reg.all]
