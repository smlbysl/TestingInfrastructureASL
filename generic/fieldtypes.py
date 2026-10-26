"""Özel alan tipleri.

Her özel alan tipi, mesajın yaşam döngüsünde ne yapacağını kendisi bilir:
- on_init(msg)          : nesne oluşturulurken
- on_send(msg)          : pack() sırasında (kullanıcı callout'larından sonra)
- on_receive(msg, raw)  : gelen paket doğrulanırken; False dönerse paket geçersiz

BaseMessageStructure bu tipteki alanları _order sırasıyla dolaşıp çağırır; isimlerini bilmez.
Projeye özel tipler (örn. Length16, CRC16) bunlardan türetilir.
"""
import ctypes
from ctypes import Structure


class FieldType(Structure):
    _pack_ = 1
    _order = 0                           # küçük olan önce çalışır

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

    # ---------------------------------------------------------------- hook'lar

    def on_init(self, msg) -> None:
        pass

    def on_send(self, msg) -> None:
        pass

    def on_receive(self, msg, raw: bytes) -> bool:
        return True

    # ---------------------------------------------------------------- yardımcılar

    def offset_in(self, msg) -> int:
        """Alanın mesaj içindeki byte offset'i."""
        return ctypes.addressof(self) - ctypes.addressof(msg)

    def from_raw(self, msg, raw: bytes):
        """Aynı alanın gelen paketteki değeri (kendi tipiyle)."""
        return type(self).from_buffer_copy(raw, self.offset_in(msg))


class LengthType(FieldType):
    """Mesajın toplam uzunluğu (header + payload + footer)."""

    def on_init(self, msg) -> None:
        self.val = ctypes.sizeof(msg)

    def on_receive(self, msg, raw: bytes) -> bool:
        return self.from_raw(msg, raw).val == ctypes.sizeof(msg)


class CounterType(FieldType):
    """Her gönderimde bir artar."""

    def on_send(self, msg) -> None:
        self.val += 1


class ChecksumType(FieldType):
    """Kendinden önceki byte'ları kapsar. Alt sınıf algoritmayı compute içinde tanımlar."""
    _order = 100                         # her zaman en son: diğer alanların yeni değerini kapsamalı

    def compute(self, data: bytes) -> int:
        raise NotImplementedError

    def on_init(self, msg) -> None:
        self.on_send(msg)

    def on_send(self, msg) -> None:
        self.val = self.compute(bytes(msg)[:self.offset_in(msg)])

    def on_receive(self, msg, raw: bytes) -> bool:
        return self.from_raw(msg, raw).val == self.compute(raw[:self.offset_in(msg)])


class AsciiType(FieldType):
    def on_get(self, v):
        return v.decode("ascii")

    def on_set(self, v):
        return v.encode("ascii")
