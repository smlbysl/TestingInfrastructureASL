"""Dispatcher: delivers a received frame to its message object and publishes the result.

frame -> ProjectX.lookup(channel, raw) -> msg.decode(raw, timestamp) -> event
- no message matches          -> UnknownReceived, frame kept in `unknown`
- matches but fails validate  -> InvalidReceived
- matches and valid           -> MessageReceived
"""
from collections import deque
from typing import Optional, Sequence

from comm.transport import RxFrame
from events.bus import EventBus
from events.types import InvalidReceived, MessageReceived, UnknownReceived
from generic.basemessage import BaseMessageStructure


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
            self.bus.publish(UnknownReceived(frame.channel, frame.data, frame.host_time, frame.timestamp))
            return None
        if not msg.decode(frame.data, frame.timestamp):
            self.bus.publish(InvalidReceived(msg, frame.data, frame.host_time, frame.timestamp))
            return None
        self.bus.publish(MessageReceived(msg, frame.data, frame.host_time, frame.timestamp))
        return msg

    def _lookup(self, frame: RxFrame) -> Optional[BaseMessageStructure]:
        for project in self.projects:
            msg = project.lookup(frame.channel, frame.data)
            if msg is not None:
                return msg
        return None
