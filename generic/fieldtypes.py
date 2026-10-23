"""Özel alan tipleri.

BaseMessageStructure, mesajın _fields_ listesinde bu tiplerden birini görünce
alanın adını kendisi bulur (length / counter / checksum) ve işlemleri buradan çağırır.
Projeye özel tipler (örn. Length16, CRC16) bunlardan türetilir.
"""
from ctypes import Structure


class FieldType(Structure):
    _pack_ = 1

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


class LengthType(FieldType):
    """Mesajın toplam uzunluğu (header + payload + footer); nesne oluşunca otomatik set edilir."""


class CounterType(FieldType):
    """Her gönderimde (pack) bir artar."""

    def next(self) -> None:
        self.val += 1


class ChecksumType(FieldType):
    """Alt sınıf algoritmayı compute içinde tanımlar."""

    def compute(self, data: bytes) -> int:
        raise NotImplementedError


class AsciiType(FieldType):
    def on_get(self, v):
        return v.decode("ascii")

    def on_set(self, v):
        return v.encode("ascii")
