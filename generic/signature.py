"""Signature: proje başına tek tanım.

Alan listesinden offset ve mask (bytes, paketteki sırayla) çıkarır, ham paketten tek bir ID üretir.
- Mask: ilgili bitler 1, ilgisizler 0. Mask uzunluğu = kontrol uzunluğu.
- compute(raw): raw[offset:offset+len(mask)] & mask -> int.from_bytes(.., endian)
- Aynı fonksiyon hem ham pakette hem bytes(obj)'de çalışır; registry anahtarıyla her zaman eşleşir.
"""
import ctypes
from typing import Optional


def field_bits(descriptor, byte_length: int) -> tuple[int, int]:
    """(bit_length, bit_offset) döner. Bitfield değilse (byte_length*8, 0)."""
    # Python 3.14+: CField'in ayrı bit_size / bit_offset alanları var
    if hasattr(descriptor, "bit_size"):
        return descriptor.bit_size, descriptor.bit_offset
    # Python <= 3.13: bitfield ise size = (bit_length << 16) | bit_offset
    bits, shift = descriptor.size >> 16, descriptor.size & 0xFFFF
    if bits == 0:
        bits, shift = byte_length * 8, 0
    return bits, shift


def find_field_type(msg_cls, name: str):
    """Alanın tipini, miras alınan sınıflar dahil _fields_ içinden bulur.

    ctypes'ta alt sınıfın _fields_'ı sadece kendi eklediği alanları içerir;
    signature alanları çoğu zaman proje sınıfında tanımlıdır.
    """
    for klass in msg_cls.__mro__:
        for f in klass.__dict__.get("_fields_", []):
            if f[0] == name:
                return f[1]
    raise AttributeError(f"{msg_cls.__name__} içinde '{name}' alanı yok")


class Signature:
    def __init__(self, *fields: str):
        self.fields = fields                 # örn. ("destinationId", "messageId")
        self.offset: Optional[int] = None    # kontrolün başladığı byte
        self.mask: Optional[bytes] = None    # paketteki byte sırasıyla
        self.endian: Optional[str] = None    # "big" / "little"
        self._checked: set[type] = set()     # bind kontrolünden geçmiş sınıflar

    @staticmethod
    def _layout(msg_cls, fields) -> tuple[int, bytes, str]:
        endian = "big" if issubclass(msg_cls, ctypes.BigEndianStructure) else "little"

        parts: list[tuple[int, bytes]] = []
        for name in fields:
            d = getattr(msg_cls, name)                     # ctypes alan tanımlayıcısı
            length = ctypes.sizeof(find_field_type(msg_cls, name))
            bits, shift = field_bits(d, length)
            field_mask = ((1 << bits) - 1) << shift
            # Endian dönüşümü burada: mask paketteki gerçek byte sırasına oturur
            parts.append((int(d.offset), field_mask.to_bytes(length, endian)))

        start = min(o for o, _ in parts)
        end = max(o + len(m) for o, m in parts)
        mask = bytearray(end - start)
        for o, m in parts:
            for i, b in enumerate(m):
                mask[o - start + i] |= b     # OR: aynı byte'ı paylaşan alanlar korunur
        return start, bytes(mask), endian

    def bind(self, msg_cls) -> None:
        """Offset, mask ve endian'ı hesaplar.

        __init_subclass__ anında ctypes layout'u hazır olmadığı için ilk nesne
        oluşturulurken çağrılır. İlk sınıf tanımı belirler; sonraki her sınıf bir kez
        bununla karşılaştırılır, uyuşmazsa ICD'ye aykırı tanım olarak hata verir.
        """
        if msg_cls in self._checked:
            return
        layout = self._layout(msg_cls, self.fields)
        if self.mask is None:
            self.offset, self.mask, self.endian = layout
        elif layout != (self.offset, self.mask, self.endian):
            raise ValueError(
                f"{msg_cls.__name__}: signature alanlarının yeri/boyu projedeki diğer "
                f"mesajlarla uyuşmuyor (offset={layout[0]}, mask={layout[1].hex()}; "
                f"beklenen offset={self.offset}, mask={self.mask.hex()})")
        self._checked.add(msg_cls)

    def compute(self, raw: bytes) -> Optional[int]:
        """Ham paketi (ya da bytes(obj)) offset+mask ile maskeleyip tek ID döndürür."""
        if self.mask is None or self.offset is None:
            return None
        chunk = raw[self.offset:self.offset + len(self.mask)]
        if len(chunk) < len(self.mask):
            return None                      # paket kısa
        masked = bytes(b & m for b, m in zip(chunk, self.mask))
        return int.from_bytes(masked, self.endian)


# v1.0 uyumluluğu
SignatureClass = Signature
