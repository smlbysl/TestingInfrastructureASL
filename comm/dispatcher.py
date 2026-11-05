"""Dispatcher: delivers a received frame to its message object and publishes the result.

frame -> ProjectX.lookup(channel, data) -> msg.decode(data, timestamp) -> event
- no channel or no message matches -> UnknownReceived, frame kept in `unknown`
- matches but fails validate       -> InvalidReceived
- matches and valid                -> MessageReceived
"""
import logging
from collections import deque
from typing import Optional, Sequence

from comm.transport import RxFrame
from events.bus import EventBus
from events.types import InvalidReceived, MessageReceived, UnknownReceived
from generic.basemessage import BaseMessageStructure

log = logging.getLogger(__name__)


class Dispatcher:
    def __init__(self, bus: EventBus, projects: Sequence[type[BaseMessageStructure]],
                 history: int = 1000):
        self.bus = bus
        self.projects = projects
        self.unknown: deque[RxFrame] = deque(maxlen=history)   # frames that matched no message

    def dispatch(self, frame: RxFrame) -> Optional[BaseMessageStructure]:
        msg = self._lookup(frame)
        if msg is None:
            self.unknown.append(frame)
            log.debug("unknown packet on %s (%s): %s", frame.link.name, frame.channel, frame.wire.hex(" "))
            self.bus.publish(UnknownReceived(frame.link, frame.channel, frame.data, frame.wire,
                                             frame.host_time, frame.timestamp))
            return None
        if not msg.decode(frame.data, frame.timestamp):
            log.warning("invalid %s on %s (size, length or checksum): %s",
                        type(msg).__name__, msg._channel, frame.wire.hex(" "))
            self.bus.publish(InvalidReceived(msg, frame.data, frame.wire, frame.host_time,
                                             timestamp=frame.timestamp))
            return None
        self.bus.publish(MessageReceived(msg, frame.data, frame.wire, frame.host_time, bytes(msg),
                                         frame.timestamp))
        return msg

    def _lookup(self, frame: RxFrame) -> Optional[BaseMessageStructure]:
        if frame.channel is None:
            return None
        for project in self.projects:
            msg = project.lookup(frame.channel, frame.data)
            if msg is not None:
                return msg
        return None
