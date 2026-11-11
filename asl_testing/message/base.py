"""Base class of all messages.

Class hierarchy:
    BaseMessageStructure -> project -> family -> message class -> object

    project        derives directly from BaseMessageStructure; byte order, header fields,
                   default channel / direction / timing, list of families
    family         defines its own _signature and opens its own Registry
    message class  adds the payload fields (_fields_)
    object         may override channel, direction, timing and history per instance

Naming: _x_ belongs to ctypes (_fields_, _pack_), _x is a class setting, public information is a property.

Wire layout:
    ctypes layout:  [ body ............. | unused (variable size) | trailer ]
    on the wire:    [ body (body_size)   | trailer ]
The trailer is the checksum field (the last field). For a fixed-size message the wire equals bytes(self).
"""
from __future__ import annotations

__author__ = "İsmail Baysal"

import ctypes
import logging
import time
from ctypes import Structure
from typing import Callable, ClassVar, Optional

from asl_testing.channel.channel import Channel
from asl_testing.message.timing import Direction
from asl_testing.message.fields import ChecksumType, FieldType, LengthType
from asl_testing.message.history import MessageHistory, Record, next_seq
from asl_testing.message.registry import Registry
from asl_testing.message.signature import Signature
from asl_testing.message.state import RxState, TxState
from asl_testing.message.timing import Timing

_log = logging.getLogger(__name__)

Callout = Callable[["BaseMessageStructure"], None]


def _explicit_none(cls) -> bool:
    """True if the class sets `_signature = None` itself: its RX messages are found by channel."""
    return "_signature" in cls.__dict__ and cls.__dict__["_signature"] is None


class BaseMessageStructure(Structure):
    """Base of all messages (see the module docstring)."""
    _pack_ = 1

    _special: ClassVar[list[tuple[int, str]]] = []      # (order, name) of the FieldType fields
    _defaults: ClassVar[dict[str, object]] = {}         # defaults declared by this class
    _all_defaults: ClassVar[dict[str, object]] = {}     # merged with the base classes

    _signature: ClassVar[Optional[Signature]] = None
    _families: ClassVar[list[Registry]]                 # set on the project
    _registry: ClassVar[Registry]                       # set on the project and on each family

    _variable_size: ClassVar[bool] = False              # real size is in the length field

    _channel: ClassVar[Optional[Channel]] = None
    _direction: ClassVar[Direction] = Direction.RX
    _timing: ClassVar[Timing] = Timing()
    _history: ClassVar[int] = 64                        # received packets kept per object

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        own = [(ftype._order, name) for name, ftype, *_ in cls.__dict__.get("_fields_", [])
               if isinstance(ftype, type) and issubclass(ftype, FieldType)]
        cls._special = sorted(cls._special + own)

        merged: dict[str, object] = {}
        for klass in reversed(cls.__mro__):             # subclass wins
            merged.update(klass.__dict__.get("_defaults", {}))
        cls._all_defaults = merged

        if BaseMessageStructure in cls.__bases__:       # project
            cls._families = []
            cls._registry = Registry(cls.__dict__.get("_signature"), _explicit_none(cls))
            cls._families.append(cls._registry)
        elif "_signature" in cls.__dict__:              # family
            cls._registry = Registry(cls._signature, _explicit_none(cls))
            cls._families.append(cls._registry)

    def __init__(self, *args,
                 channel: Optional[Channel] = None,
                 direction: Optional[Direction] = None,
                 rx: Optional[Timing] = None,
                 tx: Optional[Timing] = None,
                 history: Optional[int] = None,
                 **kw):
        self._apply_defaults()
        super().__init__(*args, **kw)                   # field values given here override the defaults

        # Object settings start with "_" so they do not clash with ICD field names.
        self._channel = channel if channel is not None else type(self)._channel
        if self._channel is None:
            raise AttributeError(f"{type(self).__name__}: no channel "
                                 f"(pass channel= or define _channel on the class)")
        self._direction = direction if direction is not None else type(self)._direction
        self._rx = None
        if Direction.RX in self._direction:
            capacity = history if history is not None else type(self)._history
            self._rx = RxState(rx or self._timing, history=MessageHistory(capacity, type(self).__name__))
        self._tx = TxState(tx or self._timing) if Direction.TX in self._direction else None
        self._on_receive: list[Callout] = []
        self._on_send: list[Callout] = []
        self._last_rx_image = b""

        for field in self._special_fields():
            field.on_init(self)

        self._signature_id: Optional[int] = None
        if self._signature is not None:
            self._signature.bind(type(self))            # the ctypes layout exists only from here on
            self._signature_id = self._signature.compute(bytes(self))

        self._registry.add(self)

    # ---------------------------------------------------------------- information

    @property
    def channel(self) -> Channel:
        return self._channel

    @property
    def direction(self) -> Direction:
        return self._direction

    @property
    def signature_id(self) -> Optional[int]:
        return self._signature_id

    @property
    def rx_state(self) -> Optional[RxState]:
        return self._rx

    @property
    def tx_state(self) -> Optional[TxState]:
        return self._tx

    # The rx_ prefix keeps ICD fields such as "timestamp" from hiding these properties.

    @property
    def rx_timestamp(self) -> Optional[float]:
        """UTS time of the last valid packet in seconds, or None."""
        return self._rx.timestamp if self._rx is not None else None

    @property
    def rx_host_time(self) -> Optional[float]:
        """Host time (time.time) of the last valid packet, or None."""
        return self._rx.host_time if self._rx is not None else None

    @property
    def rx_age(self) -> Optional[float]:
        """Seconds since the last valid packet on the host clock, or None."""
        return self._rx.age() if self._rx is not None else None

    @property
    def rx_history(self) -> Optional[MessageHistory]:
        """Last received packets in order; None for a TX-only message."""
        return self._rx.history if self._rx is not None else None

    def snapshot(self):
        """Copy of the current values, taken in one step; use it to read several fields together."""
        return type(self).from_buffer_copy(bytes(self))

    def has_new(self) -> int:
        """Valid packets received since the last call; clears the count."""
        return self._rx.check_new() if self._rx is not None else 0

    def peek_new(self) -> int:
        """Like has_new() without clearing."""
        return self._rx.peek_new() if self._rx is not None else 0

    def has_sent(self) -> int:
        """Successful sends since the last call; clears the count."""
        return self._tx.check_sent() if self._tx is not None else 0

    def peek_sent(self) -> int:
        """Like has_sent() without clearing."""
        return self._tx.peek_sent() if self._tx is not None else 0

    # ---------------------------------------------------------------- defaults

    def initialize(self) -> None:
        """Restores the class defaults and recomputes length / checksum.

        Signature fields must not be in _defaults, or the registry key breaks.
        """
        self._apply_defaults()
        for field in self._special_fields():
            field.on_init(self)

    # ---------------------------------------------------------------- callouts

    def on_receive(self, callout: Callout) -> Callout:
        """Registers callout(msg), called in the RX thread after a valid packet is written. Usable as decorator."""
        self._on_receive.append(callout)
        return callout

    def on_send(self, callout: Callout) -> Callout:
        """Registers callout(msg), called in pack() before length / counter / checksum. Usable as decorator."""
        self._on_send.append(callout)
        return callout

    # ---------------------------------------------------------------- project

    @classmethod
    def families(cls, channel: Optional[Channel] = None) -> list[Registry]:
        """Registries of the project; with a channel, only those receiving on it."""
        if channel is None:
            return list(cls._families)
        return [reg for reg in cls._families if channel in reg.channels]

    @classmethod
    def lookup(cls, channel: Channel, raw: bytes) -> Optional[BaseMessageStructure]:
        """Message object of this project for a raw packet: signature match first, then by channel."""
        msg = cls.lookup_signature(channel, raw)
        return msg if msg is not None else cls.lookup_channel(channel)

    @classmethod
    def lookup_signature(cls, channel: Channel, raw: bytes) -> Optional[BaseMessageStructure]:
        for reg in cls.families(channel):
            if reg.signature is not None:
                msg = reg.lookup(channel, raw)
                if msg is not None:
                    return msg
        return None

    @classmethod
    def lookup_channel(cls, channel: Channel) -> Optional[BaseMessageStructure]:
        for reg in cls.families(channel):
            if reg.by_channel:
                msg = reg.dispatch.get((channel, None))
                if msg is not None:
                    return msg
        return None

    @classmethod
    def clear_registry(cls) -> None:
        """Drops every registered object of the project (between tests)."""
        for reg in cls._families:
            reg.clear()

    # ---------------------------------------------------------------- sizes

    def body_size(self) -> int:
        """Bytes sent before the checksum. Variable-size messages override this for TX."""
        return self._trailer_offset()

    def wire_size(self) -> int:
        """Total size on the wire (the value of the length field)."""
        return self.body_size() + self._trailer_size()

    # ---------------------------------------------------------------- RX

    def validate(self, raw: bytes) -> bool:
        """Checks the size and the special fields (length, checksum ...) of a packet.

        An exception in a field hook makes the packet invalid; it is logged.
        """
        try:
            if len(raw) < self._rx_size(raw):
                return False
            return all(field.on_receive(self, raw) for field in self._special_fields())
        except Exception:
            _log.exception("validate of %s failed on a %d byte packet", type(self).__name__, len(raw))
            return False

    def decode(self, raw: bytes, timestamp: Optional[float] = None) -> bool:
        """Writes a valid packet into the object; returns False for an invalid one.

        The new values are prepared in a separate buffer and copied in one step, so a reader
        in another thread sees either the old or the new packet. The unused part of a
        variable-size message is cleared. timestamp is the UTS time in seconds.
        """
        if not self.validate(raw):
            if self._rx is not None:
                self._rx.on_error()
            return False
        body, offset, size = self._rx_body(raw), self._trailer_offset(), self._trailer_size()
        image = bytearray(ctypes.sizeof(self))
        image[:body] = raw[:body]
        image[offset:offset + size] = raw[body:body + size]
        memoryview(self).cast("B")[:] = image
        if self._rx is not None:
            self._rx.on_receive(timestamp)
            self._rx.history.push(Record(next_seq(), timestamp, time.time(), bytes(image), type(self)))
        self._last_rx_image = bytes(image)              # MessageReceived carries these bytes
        for callout in self._on_receive:
            callout(self)
        return True

    # ---------------------------------------------------------------- TX

    def pack(self) -> bytes:
        """Bytes to send: callouts, then length / counter / checksum, then the wire bytes.

        The special fields are computed on a copy and the bytes come from that copy, so a field
        written by another thread at the same time cannot be sent with an old checksum. Only the
        special fields that changed are written back to the object.
        """
        return self._pack()[0]

    def _pack(self) -> tuple[bytes, bytes]:
        """(wire bytes, image) from the same copy; the image goes into MessageSent."""
        for callout in self._on_send:
            callout(self)
        copy = type(self).from_buffer_copy(bytes(self))
        copy.__dict__.update(self.__dict__)             # hooks see channel, states and own attributes
        before = bytes(copy)
        for field in copy._special_fields():
            field.on_send(copy)
        image = bytes(copy)
        self._write_special_fields(image, before)
        return image[:copy.body_size()] + image[copy._trailer_offset():], image

    def _sent(self) -> None:
        """Called by the TX layer after a successful send: counts it, runs after_send."""
        if self._tx is not None:
            self._tx.on_send()
        for field in self._special_fields():
            field.after_send(self)

    # ---------------------------------------------------------------- helpers

    def _apply_defaults(self) -> None:
        for name, value in self._all_defaults.items():
            field = getattr(self, name)
            if isinstance(field, FieldType):
                field.val = value
            else:
                setattr(self, name, value)

    def _special_fields(self) -> list[FieldType]:
        """Special fields of this object in _order (views on the same buffer)."""
        return [getattr(self, name) for _, name in self._special]

    def _write_special_fields(self, image: bytes, before: bytes) -> None:
        """Copies the special fields that differ between before and image; other fields stay as they are."""
        view = memoryview(self).cast("B")
        for _, name in self._special:
            descriptor = getattr(type(self), name)
            start, end = descriptor.offset, descriptor.offset + descriptor.size
            if image[start:end] != before[start:end]:
                view[start:end] = image[start:end]

    def _find_field(self, kind: type) -> Optional[FieldType]:
        for field in self._special_fields():
            if isinstance(field, kind):
                return field
        return None

    def _trailer_offset(self) -> int:
        """Offset of the checksum field; the full size if there is none."""
        checksum = self._find_field(ChecksumType)
        return checksum.offset_in(self) if checksum is not None else ctypes.sizeof(self)

    def _trailer_size(self) -> int:
        return ctypes.sizeof(self) - self._trailer_offset()

    def _rx_size(self, raw: bytes) -> int:
        """Size of an incoming packet; read from the length field for a variable-size message."""
        if self._variable_size:
            return self._find_field(LengthType).from_raw(self, raw).val
        return ctypes.sizeof(self)

    def _rx_body(self, raw: bytes) -> int:
        """Bytes of an incoming packet before its checksum."""
        return self._rx_size(raw) - self._trailer_size()
