"""Dispatcher: delivers a received frame to its message object and publishes the result.

frame -> channel registry (PCI, then signature) -> msg.decode(sdu, timestamp) -> event
- no channel accepted it, or no message on the channel matches -> UnknownReceived, frame kept in `unknown`
- matches but fails validate  -> InvalidReceived
- matches and valid           -> MessageReceived
Logs: unknown and invalid packets as WARNING, every valid packet as DEBUG.
"""
import logging
from collections import deque
from typing import Optional

from asl_testing.events.bus import EventBus
from asl_testing.events.types import InvalidReceived, MessageReceived, UnknownReceived
from asl_testing.message.base import BaseMessageStructure
from asl_testing.runtime.transport import RxFrame


class Dispatcher:
    def __init__(self, bus: EventBus, history: int = 1000, log=None):
        self.bus = bus
        self.log = log or logging.getLogger(__name__)
        self.unknown: deque[RxFrame] = deque(maxlen=history)   # frames that matched no message

    def dispatch(self, frame: RxFrame) -> Optional[BaseMessageStructure]:
        msg = frame.channel.registry.identify(frame.pdu) if frame.channel is not None else None
        if msg is None:
            pci = frame.pdu.pci if frame.pdu is not None else None
            self.unknown.append(frame)
            self.log.warning("unknown packet on %s %s(%d bytes)", frame.channel or frame.protocol,
                             f"{pci} " if pci else "", len(frame.data))
            self.bus.publish(UnknownReceived(frame.channel, frame.data, frame.host_time, frame.timestamp, pci))
            return None
        if not msg.decode(frame.pdu.sdu, frame.timestamp):
            self.log.warning("invalid %s on %s (%d bytes)", type(msg).__name__, frame.channel, len(frame.data))
            self.bus.publish(InvalidReceived(msg, frame.data, frame.host_time, b"", frame.timestamp))
            return None
        self.log.debug("RX %s on %s (%d bytes)", type(msg).__name__, frame.channel, len(frame.data))
        self.bus.publish(MessageReceived(msg, frame.data, frame.host_time, bytes(msg), frame.timestamp))
        return msg
