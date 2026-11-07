"""Signature: derives offset and mask from a list of fields and produces a single ID from a raw packet.

- Mask: relevant bits are 1, others 0 (in the byte order of the packet). Mask length = checked length.
- compute(raw): raw[offset:offset+len(mask)] & mask -> int.from_bytes(.., endian)
- The same function works on a raw packet and on bytes(object); it always matches the registry key.
"""
import ctypes
from typing import Optional


def field_bits(descriptor, byte_length: int) -> tuple[int, int]:
    """Returns (bit_length, bit_offset). For a non-bitfield: (byte_length*8, 0)."""
    # Python 3.14+: CField has separate bit_size / bit_offset attributes
    if hasattr(descriptor, "bit_size"):
        return descriptor.bit_size, descriptor.bit_offset
    # Python <= 3.13: for a bitfield, size = (bit_length << 16) | bit_offset
    bits, shift = descriptor.size >> 16, descriptor.size & 0xFFFF
    if bits == 0:
        bits, shift = byte_length * 8, 0
    return bits, shift


def find_field_type(msg_cls, name: str):
    """Finds the type of a field in _fields_, including inherited classes.

    In ctypes a subclass's _fields_ only lists the fields it adds;
    signature fields are usually defined on the project class (the header).
    """
    for klass in msg_cls.__mro__:
        for f in klass.__dict__.get("_fields_", []):
            if f[0] == name:
                return f[1]
    raise AttributeError(f"{msg_cls.__name__} has no field '{name}'")


class Signature:
    def __init__(self, *fields: str):
        self.fields = fields                 # e.g. ("destinationId", "messageId")
        self.offset: Optional[int] = None    # byte where the check starts
        self.mask: Optional[bytes] = None    # in the byte order of the packet
        self.endian: Optional[str] = None    # "big" / "little"

    def bind(self, msg_cls) -> None:
        """Computes offset, mask and endianness once.

        The ctypes layout is not ready in __init_subclass__, so this is called
        when the first object is created (inside __init__).
        """
        if self.mask is not None:
            return
        self.endian = "big" if issubclass(msg_cls, ctypes.BigEndianStructure) else "little"

        # Start byte of each field and its mask in the byte order of the packet
        parts: list[tuple[int, bytes]] = []
        for name in self.fields:
            d = getattr(msg_cls, name)                     # ctypes field descriptor
            length = ctypes.sizeof(find_field_type(msg_cls, name))
            bits, shift = field_bits(d, length)
            field_mask = ((1 << bits) - 1) << shift
            # Endianness is applied here: the mask lands on the real byte order of the packet
            parts.append((int(d.offset), field_mask.to_bytes(length, self.endian)))

        # Find the range covering all fields and merge them into one mask
        start = min(o for o, _ in parts)
        end = max(o + len(m) for o, m in parts)
        mask = bytearray(end - start)
        for o, m in parts:
            for i, b in enumerate(m):
                mask[o - start + i] |= b     # OR: fields sharing a byte are kept

        self.offset = start
        self.mask = bytes(mask)

    def compute(self, raw: bytes) -> Optional[int]:
        """Masks a raw packet (or bytes(object)) with offset+mask and returns a single ID."""
        if self.mask is None or self.offset is None:
            return None
        chunk = raw[self.offset:self.offset + len(self.mask)]
        if len(chunk) < len(self.mask):
            return None                      # packet too short
        masked = bytes(b & m for b, m in zip(chunk, self.mask))
        return int.from_bytes(masked, self.endian)
