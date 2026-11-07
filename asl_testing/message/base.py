from __future__ import annotations

import ctypes
from ctypes import Structure
from typing import Callable, ClassVar, Optional

from asl_testing.channel.channel import Channel
from asl_testing.message.timing import Direction
from asl_testing.message.fields import ChecksumType, FieldType, LengthType
from asl_testing.message.registry import Registry
from asl_testing.message.signature import Signature
from asl_testing.message.state import RxState, TxState
from asl_testing.message.timing import Timing

Callout = Callable[["BaseMessageStructure"], None]


class BaseMessageStructure(Structure):
    """Base of all messages.

    Hierarchy:  BaseMessageStructure -> Project -> Family -> message class -> object
    - Project: a class that derives DIRECTLY from BaseMessageStructure. Endianness (ctypes base),
      header fields, default channel/direction/timing. Holds the list of its families (_families).
    - Family: a class that defines its own _signature. Opens its own Registry.
      The project also opens a registry (for messages that belong to no family).
    - Message class: payload via _fields_.
    - Object: channel, direction and timing per object (class defaults otherwise).

    Naming: _x_ belongs to ctypes only (_fields_, _pack_); class settings are _x;
    public information is exposed as properties (channel, direction, signature_id, rx_state, tx_state).
    """
    _pack_ = 1

    # Special fields: (_order, field name), collected from FieldType entries in _fields_
    _special: ClassVar[list[tuple[int, str]]] = []

    # Default field values: _defaults is what the class itself declares,
    # _all_defaults is the merge with all base classes (computed, subclass wins)
    _defaults: ClassVar[dict[str, object]] = {}
    _all_defaults: ClassVar[dict[str, object]] = {}

    # Project / family
    _signature: ClassVar[Optional[Signature]] = None
    _families: ClassVar[list[Registry]]          # defined on the project
    _registry: ClassVar[Registry]                # defined on the project or the family

    # Variable size: the real packet size is in the length field (the ctypes layout is the maximum).
    # On the wire the checksum (last field) follows the used body directly.
    _variable_size: ClassVar[bool] = False

    # Defaults (can be overridden per object)
    _channel: ClassVar[Optional[Channel]] = None
    _direction: ClassVar[Direction] = Direction.RX
    _timing: ClassVar[Timing] = Timing()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        own = [(ftype._order, name) for name, ftype, *_ in cls.__dict__.get("_fields_", [])
               if isinstance(ftype, type) and issubclass(ftype, FieldType)]
        cls._special = sorted(cls._special + own)       # inherited + own fields

        merged: dict[str, object] = {}
        for klass in reversed(cls.__mro__):             # top to bottom: subclass wins
            merged.update(klass.__dict__.get("_defaults", {}))
        cls._all_defaults = merged

        if BaseMessageStructure in cls.__bases__:       # project
            cls._families = []
            cls._registry = Registry(cls.__dict__.get("_signature"))
            cls._families.append(cls._registry)
        elif "_signature" in cls.__dict__:              # family
            cls._registry = Registry(cls._signature)
            cls._families.append(cls._registry)         # the project's list, via inheritance

    def __init__(self, *args,
                 channel: Optional[Channel] = None,
                 direction: Optional[Direction] = None,
                 rx: Optional[Timing] = None,
                 tx: Optional[Timing] = None,
                 **kw):
        # Defaults first; values given to the constructor override them
        self._apply_defaults()
        # Metadata comes as keywords; ctypes fields go to super()
        super().__init__(*args, **kw)

        # Object information is stored with an underscore: no clash with an ICD field of the same name
        self._channel = channel if channel is not None else type(self)._channel
        if self._channel is None:
            raise AttributeError(f"{type(self).__name__}: no channel "
                                 f"(pass channel= or define _channel on the class)")
        self._direction = direction if direction is not None else type(self)._direction
        self._rx = RxState(rx or self._timing) if Direction.RX in self._direction else None
        self._tx = TxState(tx or self._timing) if Direction.TX in self._direction else None
        self._on_receive: list[Callout] = []
        self._on_send: list[Callout] = []

        for field in self._special_fields():
            field.on_init(self)

        self._signature_id: Optional[int] = None
        if self._signature is not None:
            self._signature.bind(type(self))            # the layout is ready here
            self._signature_id = self._signature.compute(bytes(self))

        self._registry.add(self)

    # ---------------------------------------------------------------- public information

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

    # Times of the last valid packet. Prefixed with rx_ so an ICD field such as "timestamp" does not hide them.

    @property
    def rx_timestamp(self) -> Optional[float]:
        """UTS arrival time of the last valid packet (seconds); None if nothing has arrived."""
        return self._rx.timestamp if self._rx is not None else None

    @property
    def rx_host_time(self) -> Optional[float]:
        """Wall clock of this host (time.time) when the last valid packet was received; None if nothing has arrived."""
        return self._rx.host_time if self._rx is not None else None

    @property
    def rx_age(self) -> Optional[float]:
        """Seconds since the last valid packet, on this host's clock; None if nothing has arrived."""
        return self._rx.age() if self._rx is not None else None

    def has_new(self) -> int:
        """Number of valid packets received since the last call (0: none); the call clears it.

            if status.has_new():
                print(status.speed)
        """
        return self._rx.check_new() if self._rx is not None else 0

    # ---------------------------------------------------------------- defaults

    def initialize(self) -> None:
        """Brings the fields back to the class defaults; length/checksum are recomputed.

        Signature fields must not be in _defaults: calling this later would break the registry key.
        """
        self._apply_defaults()
        for field in self._special_fields():
            field.on_init(self)

    # ---------------------------------------------------------------- user callouts

    def on_receive(self, callout: Callout) -> Callout:
        """Called after a valid packet is written into the object, in the RX thread.

        Can be used as a decorator. For a listener that runs in its own thread use comm.on_receive.
        """
        self._on_receive.append(callout)
        return callout

    def on_send(self, callout: Callout) -> Callout:
        """Called inside pack(), BEFORE counter/checksum (so changes are covered by the checksum)."""
        self._on_send.append(callout)
        return callout

    # ---------------------------------------------------------------- project

    @classmethod
    def families(cls, channel: Optional[Channel] = None) -> list[Registry]:
        """The project's family registries; with a channel, only those receiving on it."""
        if channel is None:
            return list(cls._families)
        return [reg for reg in cls._families if channel in reg.channels]

    @classmethod
    def lookup(cls, channel: Channel, raw: bytes) -> Optional[BaseMessageStructure]:
        """Finds the message object in this project that a raw packet belongs to.

        Families with a signature are tried first; a family without one (identified by the channel)
        takes the packet only if no signature matched.
        """
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
            if reg.signature is None:
                msg = reg.dispatch.get((channel, None))
                if msg is not None:
                    return msg
        return None

    @classmethod
    def clear_registry(cls) -> None:
        """Clears all records of the project (between tests)."""
        for reg in cls._families:
            reg.clear()

    # ---------------------------------------------------------------- wire layout
    #
    #   ctypes layout:  [ body ............................ | unused (variable size) | trailer ]
    #   on the wire:    [ body (body_size bytes)            | trailer ]
    #
    # The trailer is the checksum field and everything after it (the checksum is the last field).
    # For a fixed-size message the body ends where the trailer starts, so the wire equals bytes(self).

    def body_size(self) -> int:
        """Bytes before the checksum that are sent. A variable-size message overrides this for TX,
        e.g. header + count * element size."""
        return self._trailer_offset()

    def wire_size(self) -> int:
        """Total size on the wire (written to the length field)."""
        return self.body_size() + self._trailer_size()

    # ---------------------------------------------------------------- RX side

    def validate(self, raw: bytes) -> bool:
        """Do the size and the special fields (length, checksum ...) of the packet match?"""
        if len(raw) < self._rx_size(raw):
            return False
        return all(field.on_receive(self, raw) for field in self._special_fields())

    def decode(self, raw: bytes, timestamp: Optional[float] = None) -> bool:
        """Writes the packet into the object's ctypes buffer in place, if it is valid.

        Body bytes go to the start of the buffer, trailer bytes to the checksum field;
        the unused part of a variable-size message is cleared.
        timestamp: arrival time reported by UTS (seconds), stored in rx_state.timestamp.
        """
        if not self.validate(raw):
            if self._rx is not None:
                self._rx.on_error()
            return False
        body, offset, size = self._rx_body(raw), self._trailer_offset(), self._trailer_size()
        address = ctypes.addressof(self)
        ctypes.memset(address, 0, ctypes.sizeof(self))
        ctypes.memmove(address, raw, body)
        ctypes.memmove(address + offset, raw[body:body + size], size)
        if self._rx is not None:
            self._rx.on_receive(timestamp)
        for callout in self._on_receive:
            callout(self)
        return True

    # ---------------------------------------------------------------- TX side

    def pack(self) -> bytes:
        """For sending: user callouts -> special fields (length, counter, checksum) -> wire bytes."""
        for callout in self._on_send:
            callout(self)
        for field in self._special_fields():
            field.on_send(self)
        if self._tx is not None:
            self._tx.on_send()
        data = bytes(self)
        return data[:self.body_size()] + data[self._trailer_offset():]

    def _sent(self) -> None:
        """Called by the TX layer after a successful send: after_send hooks of the special fields."""
        for field in self._special_fields():
            field.after_send(self)

    # ---------------------------------------------------------------- helpers

    def _apply_defaults(self) -> None:
        for name, value in self._all_defaults.items():
            field = getattr(self, name)
            if isinstance(field, FieldType):            # special types such as Ascii, Counter
                field.val = value
            else:
                setattr(self, name, value)

    def _special_fields(self) -> list[FieldType]:
        """Views of the special fields on this object, in _order (they share the buffer)."""
        return [getattr(self, name) for _, name in self._special]

    def _find_field(self, kind: type) -> Optional[FieldType]:
        for field in self._special_fields():
            if isinstance(field, kind):
                return field
        return None

    def _trailer_offset(self) -> int:
        """Offset of the checksum field in the ctypes layout (the size if there is none)."""
        checksum = self._find_field(ChecksumType)
        return checksum.offset_in(self) if checksum is not None else ctypes.sizeof(self)

    def _trailer_size(self) -> int:
        return ctypes.sizeof(self) - self._trailer_offset()

    def _rx_size(self, raw: bytes) -> int:
        """Size of the incoming packet: from its length field for a variable-size message."""
        if self._variable_size:
            return self._find_field(LengthType).from_raw(self, raw).val
        return ctypes.sizeof(self)

    def _rx_body(self, raw: bytes) -> int:
        """Body bytes of the incoming packet (everything before its checksum)."""
        return self._rx_size(raw) - self._trailer_size()
