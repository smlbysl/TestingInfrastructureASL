"""ChannelRegistry: the messages registered on one channel, and how an incoming PDU finds its message.

Messages register on their channel, so a channel only ever matches its own messages.
Identification of an incoming PDU, in this order:
  1. PCI: the slot of pdu.pci.key() (node / subnet, CAN id; one shared slot on a plain byte stream)
  2. a message without a signature takes every PDU of its slot (it must be alone there)
  3. otherwise the message whose signature (fields inside the SDU) matches
  4. nothing matches: unknown
The rules are checked when a message registers: a message without a signature next to another one, or the
same signature id twice under one signature definition, fails at definition time. Messages of families with
different signature definitions in one slot cannot be checked that way (a packet may match both; the one
registered first wins), so that case is logged as a WARNING.

The same message created again (same class, PCI, signature and direction) replaces the old object.
TX-only objects are kept (periodic sending, clearing between tests) but never take incoming packets.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from asl_testing.protocol.pdu import Pdu

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from asl_testing.channel.channel import Channel
    from asl_testing.message.base import BaseMessageStructure
    from asl_testing.message.signature import Signature


@dataclass
class _Slot:
    """RX messages under one PCI key."""
    plain: Optional[BaseMessageStructure] = None                     # takes every PDU of the slot
    signed: dict[Signature, dict[int, BaseMessageStructure]] = field(default_factory=dict)

    def check(self, msg: BaseMessageStructure, where: str) -> None:
        name = type(msg).__name__
        if self.plain is not None:
            raise ValueError(f"{where}: {type(self.plain).__name__} has no signature and takes every packet "
                             f"there; {name} cannot be told apart from it")
        if msg._signature is None:
            if self.signed:
                other = next(iter(next(iter(self.signed.values())).values()))
                raise ValueError(f"{where}: {name} has no signature, but {type(other).__name__} "
                                 f"is already registered there")
            return
        owner = self.signed.get(msg._signature, {}).get(msg._signature_id)
        if owner is not None:
            raise ValueError(f"Conflict: {name} and {type(owner).__name__} have the same {where} and "
                             f"signature 0x{msg._signature_id:X}")

    def add(self, msg: BaseMessageStructure, where: str = "") -> None:
        if msg._signature is None:
            self.plain = msg
            return
        if msg._signature not in self.signed and self.signed:
            other = next(iter(next(iter(self.signed.values())).values()))
            log.warning("%s: %s and %s use different signature definitions; a packet matching both goes "
                        "to %s (registered first)", where, type(msg).__name__, type(other).__name__,
                        type(other).__name__)
        self.signed.setdefault(msg._signature, {})[msg._signature_id] = msg

    def remove(self, msg: BaseMessageStructure) -> None:
        if self.plain is msg:
            self.plain = None
        for by_id in self.signed.values():
            for key in [k for k, m in by_id.items() if m is msg]:
                del by_id[key]
        self.signed = {sig: by_id for sig, by_id in self.signed.items() if by_id}

    def find(self, sdu: bytes) -> Optional[BaseMessageStructure]:
        if self.plain is not None:
            return self.plain
        for signature, by_id in self.signed.items():
            msg = by_id.get(signature.compute(sdu))
            if msg is not None:
                return msg
        return None

    @property
    def empty(self) -> bool:
        return self.plain is None and not self.signed


class ChannelRegistry:
    def __init__(self, channel: Channel):
        self.channel = channel
        self.all: list[BaseMessageStructure] = []                    # every object on the channel
        self.slots: dict[tuple, _Slot] = {}                          # PCI key -> RX messages
        self.periodic_rx: list[BaseMessageStructure] = []            # watched for RX timeout

    @property
    def has_rx(self) -> bool:
        """True if the channel has a message to receive (the RX poller polls its address)."""
        return bool(self.slots)

    def add(self, msg: BaseMessageStructure) -> None:
        old = self._find_same(msg)
        if old is not None:
            self.remove(old)
        if msg._rx is not None:
            key = msg._pci.key()
            slot = self.slots.get(key) or _Slot()
            slot.check(msg, self._where(msg))
            slot.add(msg, self._where(msg))
            self.slots[key] = slot
            if msg._rx.timing.is_periodic:
                self.periodic_rx.append(msg)
        self.all.append(msg)
        msg._registered = True

    def remove(self, msg: BaseMessageStructure) -> None:
        if msg in self.all:
            self.all.remove(msg)
        for key in list(self.slots):
            self.slots[key].remove(msg)
            if self.slots[key].empty:
                del self.slots[key]
        if msg in self.periodic_rx:
            self.periodic_rx.remove(msg)
        msg._registered = False             # the TX scheduler drops objects that are no longer registered

    def identify(self, pdu: Pdu) -> Optional[BaseMessageStructure]:
        """The RX message of an incoming PDU, or None (unknown)."""
        slot = self.slots.get(pdu.pci.key())
        return slot.find(pdu.sdu) if slot is not None else None

    def clear(self, owner: Optional[type] = None) -> None:
        """Removes every object, or only the objects of one project class (between tests)."""
        for msg in list(self.all):
            if owner is None or isinstance(msg, owner):
                self.remove(msg)

    def _where(self, msg: BaseMessageStructure) -> str:
        pci = str(msg._pci)
        return f"channel ({self.channel}{', ' + pci if pci else ''})"

    def _find_same(self, msg: BaseMessageStructure) -> Optional[BaseMessageStructure]:
        for m in self.all:
            if (type(m) is type(msg) and m._pci == msg._pci
                    and m._signature_id == msg._signature_id and m._direction == msg._direction):
                return m
        return None
