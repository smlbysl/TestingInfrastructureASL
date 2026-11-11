"""Dispatcher: finds the message object of a received frame, decodes it and publishes the result.

Lookup: a signature match in any project first, then a message found by channel only.

    no match            UnknownReceived (frame kept in `unknown`)
    match, invalid      InvalidReceived
    match, valid        MessageReceived
"""

__author__ = "İsmail Baysal"
import logging
from collections import deque
from typing import Optional, Sequence

from asl_testing.runtime.transport import RxFrame
from asl_testing.events.bus import EventBus
from asl_testing.events.types import InvalidReceived, MessageReceived, UnknownReceived
from asl_testing.message.base import BaseMessageStructure


class Dispatcher:
    def __init__(self, bus: EventBus, projects: Sequence[type[BaseMessageStructure]],
                 history: int = 1000, log=None):
        self.bus = bus
        self.projects = projects
        self.log = log or logging.getLogger(__name__)
        self.unknown: deque[RxFrame] = deque(maxlen=history)

    def dispatch(self, frame: RxFrame) -> Optional[BaseMessageStructure]:
        msg = self._lookup(frame)
        if msg is None:
            self.unknown.append(frame)
            self.log.warning("unknown packet on %s (%d bytes)", frame.channel, len(frame.data))
            self.bus.publish(UnknownReceived(frame.channel, frame.data, frame.host_time, frame.timestamp))
            return None
        if not msg.decode(frame.data, frame.timestamp):
            self.log.warning("invalid %s on %s (%d bytes)", type(msg).__name__, frame.channel, len(frame.data))
            self.bus.publish(InvalidReceived(msg, frame.data, frame.host_time, b"", frame.timestamp))
            return None
        self.log.debug("RX %s on %s (%d bytes)", type(msg).__name__, frame.channel, len(frame.data))
        self.bus.publish(MessageReceived(msg, frame.data, frame.host_time, msg._last_rx_image, frame.timestamp))
        return msg

    def _lookup(self, frame: RxFrame) -> Optional[BaseMessageStructure]:
        if frame.channel is None:
            return None
        for project in self.projects:
            msg = project.lookup_signature(frame.channel, frame.data)
            if msg is not None:
                return msg
        for project in self.projects:
            msg = project.lookup_channel(frame.channel)
            if msg is not None:
                return msg
        return None
