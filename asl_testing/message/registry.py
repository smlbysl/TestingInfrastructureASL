"""Registry: records of one message family (messages sharing the same signature).

A family class opens its own Registry when it is defined and adds it to its project's family list.
A message object does not know the rules; it only calls registry.add(self).
The registry holds references to the objects; decode writes incoming data directly into them.

A registry opened with by_channel (a class that writes `_signature = None` explicitly) identifies its RX
messages by the channel alone: key (channel, None), so it holds at most one RX message per channel.
A registry that simply has no signature (a project without one) does not receive anything, as before.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from asl_testing.channel.channel import Channel
from asl_testing.message.signature import Signature

if TYPE_CHECKING:
    from asl_testing.message.base import BaseMessageStructure


class Registry:
    def __init__(self, signature: Optional[Signature], by_channel: bool = False):
        self.signature = signature
        self.by_channel = by_channel                            # explicit _signature = None
        self.all: list[BaseMessageStructure] = []               # single source: all objects
        self.dispatch: dict[tuple[Channel, int], BaseMessageStructure] = {}  # RX objects only
        self.periodic_rx: list[BaseMessageStructure] = []       # watched for RX timeout
        self.periodic_tx: list[BaseMessageStructure] = []       # periodic TX candidates

    @property
    def channels(self) -> set[Channel]:
        """Channels on which this family receives."""
        return {channel for channel, _ in self.dispatch}

    def add(self, msg: BaseMessageStructure) -> None:
        # The same message created again (same class, channel, signature, direction) replaces the old one
        old = self._find_same(msg)
        if old is not None:
            self.remove(old)

        self.all.append(msg)
        if msg._rx is not None:
            if self.by_channel or msg._signature_id is not None:
                key = (msg._channel, msg._signature_id)     # (channel, None): identified by the channel
                owner = self.dispatch.get(key)
                if owner is not None:
                    what = "no signature" if key[1] is None else f"signature 0x{key[1]:X}"
                    raise ValueError(
                        f"Conflict: {type(msg).__name__} and {type(owner).__name__} have the same "
                        f"channel ({msg._channel}) and {what}")
                self.dispatch[key] = msg
            if msg._rx.timing.is_periodic:
                self.periodic_rx.append(msg)
        # TX-only objects do not enter dispatch: an incoming packet must not overwrite a TX object
        if msg._tx is not None and msg._tx.timing.is_periodic:
            self.periodic_tx.append(msg)
        msg._registered = True

    def remove(self, msg: BaseMessageStructure) -> None:
        self.all.remove(msg)
        for key in [k for k, m in self.dispatch.items() if m is msg]:
            del self.dispatch[key]
        if msg in self.periodic_rx:
            self.periodic_rx.remove(msg)
        if msg in self.periodic_tx:
            self.periodic_tx.remove(msg)
        msg._registered = False                 # the TX scheduler drops objects that are no longer registered

    def lookup(self, channel: Channel, raw: bytes) -> Optional[BaseMessageStructure]:
        """Finds the message object of this family from a raw packet."""
        if self.by_channel:
            return self.dispatch.get((channel, None))     # identified by the channel
        if self.signature is None or self.signature.mask is None:
            return None
        return self.dispatch.get((channel, self.signature.compute(raw)))

    def clear(self) -> None:
        """For cleaning up between tests."""
        for msg in self.all:
            msg._registered = False
        self.all.clear()
        self.dispatch.clear()
        self.periodic_rx.clear()
        self.periodic_tx.clear()

    def _find_same(self, msg: BaseMessageStructure) -> Optional[BaseMessageStructure]:
        for m in self.all:
            if (type(m) is type(msg) and m._channel == msg._channel
                    and m._signature_id == msg._signature_id and m._direction == msg._direction):
                return m
        return None
