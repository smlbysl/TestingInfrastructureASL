"""Special field types: fields that take part in the message life cycle.

Hooks, called by BaseMessageStructure in _order:
    on_init(msg)            object created
    on_send(msg)            inside pack(), after the user callouts
    on_receive(msg, raw)    while a packet is validated; False rejects the packet
    after_send(msg)         after a successful send (not after a UTS error)

Projects derive their own types from these (e.g. Length16, CRC16).
"""

__author__ = "İsmail Baysal"

import ctypes
from ctypes import Structure


class FieldType(Structure):
    """Base of the special field types; .val reads / writes the value through on_get / on_set."""
    _pack_ = 1
    _order = 0                           # lower runs first

    @property
    def val(self):
        return self.on_get(self.value)

    @val.setter
    def val(self, v):
        self.value = self.on_set(v)

    def on_get(self, v):
        return v

    def on_set(self, v):
        return v

    # ---------------------------------------------------------------- hooks

    def on_init(self, msg) -> None:
        pass

    def on_send(self, msg) -> None:
        pass

    def on_receive(self, msg, raw: bytes) -> bool:
        return True

    def after_send(self, msg) -> None:
        pass

    # ---------------------------------------------------------------- helpers

    def offset_in(self, msg) -> int:
        """Byte offset of the field in the message."""
        return ctypes.addressof(self) - ctypes.addressof(msg)

    def from_raw(self, msg, raw: bytes):
        """The same field read from a raw packet."""
        return type(self).from_buffer_copy(raw, self.offset_in(msg))


class LengthType(FieldType):
    """Total packet length on the wire (header + body + checksum)."""

    def on_init(self, msg) -> None:
        self.val = msg.wire_size()

    def on_send(self, msg) -> None:
        self.val = msg.wire_size()

    def on_receive(self, msg, raw: bytes) -> bool:
        length = self.from_raw(msg, raw).val
        if msg._variable_size:
            return self.min_length(msg) <= length <= ctypes.sizeof(msg)
        return length == ctypes.sizeof(msg)

    def min_length(self, msg) -> int:
        """Smallest valid length of a variable-size packet: up to the end of this field plus the checksum."""
        return self.offset_in(msg) + ctypes.sizeof(self) + msg._trailer_size()


class CounterType(FieldType):
    """Incremented on every pack()."""

    def on_send(self, msg) -> None:
        self.val += 1


class ChecksumType(FieldType):
    """Last field of a message; covers the body sent before it. Subclasses implement compute()."""
    _order = 100                         # runs last, after the other fields are final

    def compute(self, data: bytes) -> int:
        raise NotImplementedError

    def on_init(self, msg) -> None:
        self.on_send(msg)

    def on_send(self, msg) -> None:
        self.val = self.compute(bytes(msg)[:msg.body_size()])

    def on_receive(self, msg, raw: bytes) -> bool:
        body = msg._rx_body(raw)
        return type(self).from_buffer_copy(raw, body).val == self.compute(raw[:body])


class AsciiType(FieldType):
    """Text field: .val is a str, stored as ASCII bytes."""

    def on_get(self, v):
        return v.decode("ascii")

    def on_set(self, v):
        return v.encode("ascii")
