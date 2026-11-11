"""Registry: the message objects of one family.

A family class opens its registry when it is defined; every object adds itself with registry.add(self).
RX objects are stored under (channel, signature id); decode writes incoming packets directly into them.
A family that sets `_signature = None` (by_channel) is found by channel only: one RX message per channel.
"""
from __future__ import annotations

__author__ = "İsmail Baysal"

from typing import TYPE_CHECKING, Optional

from asl_testing.channel.channel import Channel
from asl_testing.message.signature import Signature

if TYPE_CHECKING:
    from asl_testing.message.base import BaseMessageStructure


class Registry:
    def __init__(self, signature: Optional[Signature], by_channel: bool = False):
        self.signature = signature
        self.by_channel = by_channel
        self.all: list[BaseMessageStructure] = []
        self.dispatch: dict[tuple[Channel, int], BaseMessageStructure] = {}     # RX objects only
        self.periodic_rx: list[BaseMessageStructure] = []                       # checked for RX timeout
        self.periodic_tx: list[BaseMessageStructure] = []

    @property
    def channels(self) -> set[Channel]:
        """Channels this family receives on."""
        return {channel for channel, _ in self.dispatch}

    def add(self, msg: BaseMessageStructure) -> None:
        """Adds an object; an object of the same class, channel, signature and direction is replaced."""
        old = self._find_same(msg)
        if old is not None:
            self.remove(old)

        self.all.append(msg)
        if msg._rx is not None:
            if self.by_channel or msg._signature_id is not None:
                key = (msg._channel, msg._signature_id)
                owner = self.dispatch.get(key)
                if owner is not None:
                    what = "no signature" if key[1] is None else f"signature 0x{key[1]:X}"
                    raise ValueError(
                        f"Conflict: {type(msg).__name__} and {type(owner).__name__} have the same "
                        f"channel ({msg._channel}) and {what}")
                self.dispatch[key] = msg
            if msg._rx.timing.is_periodic:
                self.periodic_rx.append(msg)
        # TX-only objects stay out of dispatch, so a received packet never overwrites them.
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
        msg._registered = False                         # the TX scheduler drops unregistered objects

    def lookup(self, channel: Channel, raw: bytes) -> Optional[BaseMessageStructure]:
        """Object of this family for a raw packet, or None."""
        if self.by_channel:
            return self.dispatch.get((channel, None))
        if self.signature is None or self.signature.mask is None:
            return None
        return self.dispatch.get((channel, self.signature.compute(raw)))

    def clear(self) -> None:
        """Drops every object (between tests)."""
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
