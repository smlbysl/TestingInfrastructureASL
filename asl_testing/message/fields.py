"""Special field types.

Each special field type knows what to do in the message life cycle:
- on_init(msg)          : when the object is created
- on_send(msg)          : inside pack() (after the user callouts)
- on_receive(msg, raw)  : while an incoming packet is validated; returning False rejects it
- after_send(msg)       : after the packet was sent successfully (not on a UTS error), e.g. to clear a request bit

BaseMessageStructure walks the fields of these types in _order and calls them; it does not know their names.
Project-specific types (e.g. Length16, CRC16) derive from these.
"""
import ctypes
from ctypes import Structure


class FieldType(Structure):
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
        """Byte offset of the field inside the message."""
        return ctypes.addressof(self) - ctypes.addressof(msg)

    def from_raw(self, msg, raw: bytes):
        """The same field read from the incoming packet (with its own type)."""
        return type(self).from_buffer_copy(raw, self.offset_in(msg))


class LengthType(FieldType):
    """Total length of the packet on the wire (header + body + checksum)."""

    def on_init(self, msg) -> None:
        self.val = msg.wire_size()

    def on_send(self, msg) -> None:
        self.val = msg.wire_size()              # changes with the used body of a variable-size message

    def on_receive(self, msg, raw: bytes) -> bool:
        length = self.from_raw(msg, raw).val
        if msg._variable_size:
            return length <= ctypes.sizeof(msg)  # the ctypes layout is the maximum
        return length == ctypes.sizeof(msg)


class CounterType(FieldType):
    """Incremented on every send."""

    def on_send(self, msg) -> None:
        self.val += 1


class ChecksumType(FieldType):
    """The last field of a message; covers the body sent before it.

    Subclasses define the algorithm in compute. For a variable-size message the checksum
    follows the used body on the wire, so its position changes with every packet.
    """
    _order = 100                         # always last: must cover the new values of the other fields

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
    def on_get(self, v):
        return v.decode("ascii")

    def on_set(self, v):
        return v.encode("ascii")
