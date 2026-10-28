from __future__ import annotations

import ctypes
from ctypes import Structure
from typing import Callable, ClassVar, Optional

from generic.channel import Channel
from generic.enumerations import Direction
from generic.fieldtypes import FieldType
from generic.registry import Registry
from generic.signature import Signature
from generic.state import RxState, TxState
from generic.timing import Timing

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
        """Finds the message object in this project that a raw packet belongs to."""
        for reg in cls.families(channel):
            msg = reg.lookup(channel, raw)
            if msg is not None:
                return msg
        return None

    @classmethod
    def clear_registry(cls) -> None:
        """Clears all records of the project (between tests)."""
        for reg in cls._families:
            reg.clear()

    # ---------------------------------------------------------------- RX side

    def validate(self, raw: bytes) -> bool:
        """Do the size and the special fields (length, checksum ...) of the packet match?"""
        if len(raw) < ctypes.sizeof(self):
            return False
        return all(field.on_receive(self, raw) for field in self._special_fields())

    def decode(self, raw: bytes, timestamp: Optional[float] = None) -> bool:
        """Writes the packet into the object's ctypes buffer in place, if it is valid.

        timestamp: arrival time reported by UTS (seconds), stored in rx_state.timestamp.
        """
        if not self.validate(raw):
            if self._rx is not None:
                self._rx.on_error()
            return False
        ctypes.memmove(ctypes.addressof(self), raw, ctypes.sizeof(self))
        if self._rx is not None:
            self._rx.on_receive(timestamp)
        for callout in self._on_receive:
            callout(self)
        return True

    # ---------------------------------------------------------------- TX side

    def pack(self) -> bytes:
        """For sending: user callouts -> special fields (counter, checksum) -> bytes."""
        for callout in self._on_send:
            callout(self)
        for field in self._special_fields():
            field.on_send(self)
        if self._tx is not None:
            self._tx.on_send()
        return bytes(self)

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
