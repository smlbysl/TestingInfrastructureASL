"""Signature: identifies a message by a set of its fields.

From the field list an offset and a mask are computed once; compute(raw) masks the same bytes of
a packet (or of bytes(object)) and returns one integer. That integer is the registry key.
"""

__author__ = "İsmail Baysal"

import ctypes
from typing import Optional


def field_bits(descriptor, byte_length: int) -> tuple[int, int]:
    """(bit length, bit offset) of a field; a non-bitfield gives (byte_length * 8, 0)."""
    if hasattr(descriptor, "bit_size"):                 # Python 3.14+
        return descriptor.bit_size, descriptor.bit_offset
    bits, shift = descriptor.size >> 16, descriptor.size & 0xFFFF     # Python <= 3.13 packs both into size
    if bits == 0:
        bits, shift = byte_length * 8, 0
    return bits, shift


def find_field_type(msg_cls, name: str):
    """Type of a field, searched in the class and its bases (a subclass lists only its own fields)."""
    for klass in msg_cls.__mro__:
        for f in klass.__dict__.get("_fields_", []):
            if f[0] == name:
                return f[1]
    raise AttributeError(f"{msg_cls.__name__} has no field '{name}'")


class Signature:
    def __init__(self, *fields: str):
        self.fields = fields                 # e.g. ("destinationId", "messageId")
        self.offset: Optional[int] = None    # first checked byte
        self.mask: Optional[bytes] = None    # in the packet's byte order
        self.endian: Optional[str] = None    # "big" / "little"

    def bind(self, msg_cls) -> None:
        """Computes offset, mask and byte order once (the ctypes layout is ready only at the first object)."""
        if self.mask is not None:
            return
        self.endian = "big" if issubclass(msg_cls, ctypes.BigEndianStructure) else "little"

        parts: list[tuple[int, bytes]] = []
        for name in self.fields:
            d = getattr(msg_cls, name)
            length = ctypes.sizeof(find_field_type(msg_cls, name))
            bits, shift = field_bits(d, length)
            field_mask = ((1 << bits) - 1) << shift
            parts.append((int(d.offset), field_mask.to_bytes(length, self.endian)))

        start = min(o for o, _ in parts)
        end = max(o + len(m) for o, m in parts)
        mask = bytearray(end - start)
        for o, m in parts:
            for i, b in enumerate(m):
                mask[o - start + i] |= b     # fields sharing a byte are both kept

        self.offset = start
        self.mask = bytes(mask)

    def compute(self, raw: bytes) -> Optional[int]:
        """Signature id of a raw packet, or None if the packet is too short."""
        if self.mask is None:
            return None
        chunk = raw[self.offset:self.offset + len(self.mask)]
        if len(chunk) < len(self.mask):
            return None
        masked = bytes(b & m for b, m in zip(chunk, self.mask))
        return int.from_bytes(masked, self.endian)
