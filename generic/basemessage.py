from __future__ import annotations

import ctypes
from ctypes import Structure, sizeof
from typing import ClassVar, Optional

from generic.channel import Channel
from generic.enumerations import ProtocolType, Direction
from generic.registry import ProjectRegistry
from generic.signature import Signature, field_bits, find_field_type
from generic.state import RxState, TxState


class BaseFooter(Structure):
    _crc_: Optional[str] = None

    def compute(self, data: bytes) -> int:
        raise NotImplementedError


class SignatureFilter():
    # Eski imza yapısı. Artık Signature kullanılıyor; geriye uyumluluk için duruyor.
    _offset_: Optional[int]
    _length_: Optional[int]
    _msk_: Optional[int]

    def __init__(self, offset: Optional[int] = None, length: Optional[int] = None, msk: Optional[int] = None):
        self._offset_ = offset
        self._length_ = length
        self._msk_ = msk


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


class CounterType(FieldType):
    def next(self):
        self.val += 1


class LengthType(FieldType):
    def next(self):
        self.val += 1


class ChecksumType(FieldType):
    def compute(self, data: bytes) -> int:
        raise NotImplementedError


class AsciiType(FieldType):
    def on_get(self, v):
        return v.decode("ascii")

    def on_set(self, v):
        return v.encode("ascii")


#Abstract Class
class BaseMessageStructure(Structure):
    """Tüm mesajların tabanı.

    Hiyerarşi:  BaseMessageStructure -> ProjectX (proje sınıfı) -> mesaj sınıfı
    - Proje sınıfı: BaseMessageStructure'dan DOĞRUDAN türeyen sınıf. Kendi registry'si olur.
      Signature, protokol/interface, yön, periyot gibi varsayılanlar burada class attribute.
    - Mesaj sınıfı: _fields_ ile byte formatını tanımlar.
    - Nesne: channel, yön, periyot nesne başına verilebilir (verilmezse sınıf varsayılanı).
    """
    _pack_ = 1

    _COUNTER_FIELD_NAME_: ClassVar[Optional[str]] = None
    _LENGTH_FIELD_NAME_: ClassVar[Optional[str]] = None
    _CHECKSUM_FIELD_NAME_: ClassVar[Optional[str]] = None

    #Signature Fields
    _signature: ClassVar[Optional[Signature]] = None

    #Registry: proje sınıfı -> ProjectRegistry
    _project: ClassVar[Optional[type]] = None
    _registry: ClassVar[dict[type, ProjectRegistry]] = {}

    #Communicatin Fields (varsayılanlar; nesne başına channel ile ezilebilir)
    _COMMPROTOCOL_: ClassVar[Optional[ProtocolType]] = None
    _COMMINTERFACE_: ClassVar[Optional[int]] = None

    #Message Data (varsayılanlar; nesne başına ezilebilir)
    _DIRECTION_: ClassVar[Optional[Direction]] = None
    _PERIOD_: ClassVar[Optional[float]] = None
    _RX_TOLERANCE_: ClassVar[float] = 2.0

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name, ftype, *_ in cls.__dict__.get("_fields_", []):
            if isinstance(ftype, type) and issubclass(ftype, CounterType):  cls._COUNTER_FIELD_NAME_  = name
            if isinstance(ftype, type) and issubclass(ftype, LengthType):   cls._LENGTH_FIELD_NAME_   = name
            if isinstance(ftype, type) and issubclass(ftype, ChecksumType): cls._CHECKSUM_FIELD_NAME_ = name
        # Proje sınıfı: kayıtlar signature'a değil projeye bağlı (signature'sız projeler de kayıt tutar)
        if BaseMessageStructure in cls.__bases__:
            cls._project = cls
            BaseMessageStructure._registry[cls] = ProjectRegistry()

    def __init__(self, *args,
                 channel: Optional[Channel] = None,
                 direction: Optional[Direction] = None,
                 rx_period: Optional[float] = None,
                 tx_period: Optional[float] = None,
                 rx_tolerance: Optional[float] = None,
                 **kw):
        # Metadata keyword olarak alınır, ctypes alanları super()'e gider
        super().__init__(*args, **kw)

        if channel is None and self._COMMPROTOCOL_ is not None and self._COMMINTERFACE_ is not None:
            channel = Channel(self._COMMPROTOCOL_, self._COMMINTERFACE_)
        self.channel = channel

        if direction is None:
            direction = self._DIRECTION_ if self._DIRECTION_ is not None else Direction.RX
        self.direction = direction

        rx_period = rx_period if rx_period is not None else self._PERIOD_
        tx_period = tx_period if tx_period is not None else self._PERIOD_
        tolerance = rx_tolerance if rx_tolerance is not None else self._RX_TOLERANCE_
        self.rx_state = RxState(rx_period, tolerance) if Direction.RX in direction else None
        self.tx_state = TxState(tx_period) if Direction.TX in direction else None

        self._signature_id: Optional[int] = None
        self.__post_init__()

    def __post_init__(self):
        self.__processinterface__()
        self.__processsignature__()
        self.__processlength__()
        self.__processchecksum__()
        self._register()

    def __setattr__(self, name, value):
        # Kayıttan sonra signature alanları değişirse saklanan ID ve dispatch anahtarı bozulur
        if (self.__dict__.get("_registered") and self._signature is not None
                and name in self._signature.fields):
            raise AttributeError(
                f"{type(self).__name__}.{name} signature alanı; nesne kaydedildikten sonra değiştirilemez")
        super().__setattr__(name, value)

    # ---------------------------------------------------------------- registry

    @classmethod
    def registry(cls) -> ProjectRegistry:
        if cls._project is None:
            raise TypeError(f"{cls.__name__} bir proje sınıfına bağlı değil")
        return BaseMessageStructure._registry[cls._project]

    @classmethod
    def clear_registry(cls) -> None:
        """Tüm projelerin kayıtlarını temizler (testler arası izolasyon)."""
        for reg in BaseMessageStructure._registry.values():
            reg.clear()

    def _register(self) -> None:
        reg = self.registry()
        reg.all.append(self)
        if self.rx_state is not None:
            if self._signature_id is not None:
                key = (self.channel, self._signature_id)
                owner = reg.dispatch.get(key)
                if owner is not None:
                    raise ValueError(
                        f"Çakışma: {type(self).__name__} ve {type(owner).__name__} aynı "
                        f"channel ({self.channel}) ve imzaya (0x{self._signature_id:X}) sahip")
                reg.dispatch[key] = self
            if self.rx_state.period:
                reg.periodic_rx.append(self)
        # TX-only nesneler dispatch'e girmez: gelen paket TX nesnesinin üzerine yazmasın
        if self.tx_state is not None and self.tx_state.period:
            reg.periodic_tx.append(self)
        self.__dict__["_registered"] = True

    # ---------------------------------------------------------------- RX tarafı

    @property
    def signature_id(self) -> Optional[int]:
        return self._signature_id

    @classmethod
    def lookup(cls, channel: Channel, raw: bytes) -> Optional[BaseMessageStructure]:
        """Ham paketin bu projede hangi mesaj nesnesine ait olduğunu bulur."""
        if cls._signature is None or cls._signature.mask is None:
            return None
        sid = cls._signature.compute(raw)
        return cls.registry().dispatch.get((channel, sid))

    def validate(self, raw: bytes) -> bool:
        """Gelen paketin boyu, length alanı ve checksum'ı tutuyor mu?"""
        size = ctypes.sizeof(self)
        if len(raw) < size:
            return False
        if self._LENGTH_FIELD_NAME_ is not None:
            ftype = find_field_type(type(self), self._LENGTH_FIELD_NAME_)
            offset = getattr(type(self), self._LENGTH_FIELD_NAME_).offset
            if ftype.from_buffer_copy(raw, offset).val != size:
                return False
        if self._CHECKSUM_FIELD_NAME_ is not None:
            ftype = find_field_type(type(self), self._CHECKSUM_FIELD_NAME_)
            offset = getattr(type(self), self._CHECKSUM_FIELD_NAME_).offset
            if ftype.from_buffer_copy(raw, offset).val != ftype().compute(raw[:offset]):
                return False
        return True

    def decode(self, raw: bytes) -> bool:
        """Paket geçerliyse objenin ctypes buffer'ına yerinde yazar."""
        if not self.validate(raw):
            if self.rx_state is not None:
                self.rx_state.on_error()
            return False
        ctypes.memmove(ctypes.addressof(self), raw, ctypes.sizeof(self))
        if self.rx_state is not None:
            self.rx_state.on_receive()
        return True

    # ---------------------------------------------------------------- TX tarafı

    def pack(self) -> bytes:
        """Gönderim için: counter'ı artırır, checksum'ı günceller, byte'ları döner."""
        if self._COUNTER_FIELD_NAME_ is not None:
            self._next_counter()
        if self._CHECKSUM_FIELD_NAME_ is not None:
            self._update_checksum()
        if self.tx_state is not None:
            self.tx_state.on_send()
        return bytes(self)

    # ---------------------------------------------------------------- yardımcılar

    def _update_length(self):
        if self._LENGTH_FIELD_NAME_ is not None:
            getattr(self, self._LENGTH_FIELD_NAME_).val = sizeof(self)
        else:
            raise AttributeError

    def _next_counter(self):
        if self._COUNTER_FIELD_NAME_ is not None:
            getattr(self, self._COUNTER_FIELD_NAME_).next()
        else:
            raise AttributeError

    def _get_field_info(self, fieldname: str) -> dict:
        try:
            ftype = find_field_type(type(self), fieldname)
        except AttributeError:
            return {
                "byte_offset": 0,
                "byte_length": 0,
                "bit_offset": 0,
                "bit_length": 0,
                "is_bitfield": False}

        descriptor = getattr(type(self), fieldname)
        storage_size = sizeof(ftype)
        bit_length, bit_offset = field_bits(descriptor, storage_size)

        return {
            "byte_offset": descriptor.offset,
            "byte_length": storage_size,
            "bit_offset": bit_offset,
            "bit_length": bit_length,
            "is_bitfield": bit_length != storage_size * 8}

    def _update_checksum(self) -> None:
        if self._CHECKSUM_FIELD_NAME_ is not None:
            offset = getattr(type(self), self._CHECKSUM_FIELD_NAME_).offset
            field = getattr(self, self._CHECKSUM_FIELD_NAME_)
            field.val = field.compute(bytes(self)[:offset])
        else:
            raise AttributeError

    def __processsignature__(self):
        if self._signature is None:
            return
        self._signature.bind(type(self))                 # layout burada hazır
        self._signature_id = self._signature.compute(bytes(self))

    def __processlength__(self) -> int:
        if self._LENGTH_FIELD_NAME_ is not None:
            templen = ctypes.sizeof(type(self))
            getattr(self, self._LENGTH_FIELD_NAME_).val = templen
            return templen
        return 0

    def __processchecksum__(self) -> int:
        if self._CHECKSUM_FIELD_NAME_ is not None:
            self._update_checksum()
            return getattr(self, self._CHECKSUM_FIELD_NAME_).val
        return 0

    def __processinterface__(self) -> bool:
        if self.channel is not None:
            return True
        raise AttributeError(
            f"{type(self).__name__}: channel yok (channel= verin ya da "
            f"_COMMPROTOCOL_ / _COMMINTERFACE_ tanımlayın)")

    def GetProtocolInterface(self):
        return self.channel.protocol, self.channel.interface
