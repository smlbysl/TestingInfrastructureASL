import ctypes


def field_bits(descriptor, byte_length: int):
    """(bit_length, bit_offset) döner. Bitfield değilse (byte_length*8, 0)."""
    # Python 3.14+: CField'in ayrı bit_size / bit_offset alanları var
    if hasattr(descriptor, "bit_size"):
        bits, shift = descriptor.bit_size, descriptor.bit_offset
        if bits == byte_length * 8 and shift == 0:
            return bits, 0
        return bits, shift
    # Python <= 3.13: bitfield ise size = (bit_length << 16) | bit_offset
    bits, shift = descriptor.size >> 16, descriptor.size & 0xFFFF
    if bits == 0:
        bits, shift = byte_length * 8, 0
    return bits, shift


class SignatureClass:
    def __init__(self, *fields):
        self.fields = fields
        self.endian = "little"
        self.offset = 0
        self.mask: bytes | None = None

    def bind(self, msg_cls):
        if self.mask is not None:
            return
        self.endian = ("big" if issubclass(msg_cls, ctypes.BigEndianStructure) else "little")

        parts = []
        for name in self.fields:
            d = getattr(msg_cls, name)
            ftype = _find_field_type(msg_cls, name)
            length = ctypes.sizeof(ftype)
            bits, shift = field_bits(d, length)
            field_mask = ((1 << bits) - 1) << shift
            parts.append((d.offset, field_mask.to_bytes(length, self.endian)))

        start = min(o for o, _ in parts)
        end = max(o + len(m) for o, m in parts)
        mask = bytearray(end - start)
        for o, m in parts:
            for i, b in enumerate(m):
                mask[o - start + i] |= b

        self.offset = start
        self.mask = bytes(mask)

    def compute(self, raw: bytes):
        chunk = raw[self.offset:self.offset + len(self.mask)]
        if len(chunk) < len(self.mask):
            return None
        masked = bytes(b & m for b, m in zip(chunk, self.mask))
        return int.from_bytes(masked, self.endian)


def _find_field_type(msg_cls, name):
    """Alanın tipini, miras alınan sınıflar dahil _fields_ içinden bulur."""
    for klass in msg_cls.__mro__:
        for f in klass.__dict__.get("_fields_", []):
            if f[0] == name:
                return f[1]
    raise AttributeError(f"{msg_cls.__name__} içinde '{name}' alanı yok")
