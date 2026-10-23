from __future__ import annotations

import ctypes
from ctypes import Structure
from typing import ClassVar, Optional

from generic.channel import Channel
from generic.enumerations import Direction, ProtocolType
from generic.fieldtypes import ChecksumType, CounterType, LengthType
from generic.registry import Registry
from generic.signature import Signature, find_field_type
from generic.state import RxState, TxState


class BaseMessageStructure(Structure):
    """Tüm mesajların tabanı.

    Hiyerarşi:  BaseMessageStructure -> Proje -> Aile -> mesaj sınıfı -> nesne
    - Proje: BaseMessageStructure'dan DOĞRUDAN türeyen sınıf. Endian (ctypes tabanı), header
      alanları, varsayılan channel/yön/periyot. Ailelerinin listesini (_families) tutar.
    - Aile: kendi _signature'ını tanımlayan sınıf. Kendi Registry'sini açar.
      Projenin kendisi de bir registry açar (signature'ı yoksa signature'sız mesajlar için).
    - Mesaj sınıfı: _fields_ ile payload.
    - Nesne: channel, yön, periyot nesne başına verilir (verilmezse sınıf varsayılanı).
    """
    _pack_ = 1

    # Özel alanların adları (_fields_ içindeki tipten otomatik bulunur)
    _COUNTER_FIELD_NAME_: ClassVar[Optional[str]] = None
    _LENGTH_FIELD_NAME_: ClassVar[Optional[str]] = None
    _CHECKSUM_FIELD_NAME_: ClassVar[Optional[str]] = None

    # Proje / aile
    _signature: ClassVar[Optional[Signature]] = None
    _families: ClassVar[list[Registry]]          # projede tanımlanır
    _registry: ClassVar[Registry]                # projede ya da ailede tanımlanır

    # Varsayılanlar (nesne başına ezilebilir)
    _COMMPROTOCOL_: ClassVar[Optional[ProtocolType]] = None
    _COMMINTERFACE_: ClassVar[Optional[int]] = None
    _DIRECTION_: ClassVar[Direction] = Direction.RX
    _PERIOD_: ClassVar[Optional[float]] = None
    _RX_TOLERANCE_: ClassVar[float] = 2.0

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name, ftype, *_ in cls.__dict__.get("_fields_", []):
            if isinstance(ftype, type) and issubclass(ftype, CounterType):  cls._COUNTER_FIELD_NAME_ = name
            if isinstance(ftype, type) and issubclass(ftype, LengthType):   cls._LENGTH_FIELD_NAME_ = name
            if isinstance(ftype, type) and issubclass(ftype, ChecksumType): cls._CHECKSUM_FIELD_NAME_ = name

        if BaseMessageStructure in cls.__bases__:       # proje
            cls._families = []
            cls._registry = Registry(cls.__dict__.get("_signature"))
            cls._families.append(cls._registry)
        elif "_signature" in cls.__dict__:              # aile
            cls._registry = Registry(cls._signature)
            cls._families.append(cls._registry)         # miras yoluyla projenin listesi

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
        if channel is None:
            raise AttributeError(f"{type(self).__name__}: channel yok (channel= verin ya da "
                                 f"_COMMPROTOCOL_ / _COMMINTERFACE_ tanımlayın)")
        self.channel = channel

        self.direction = direction if direction is not None else self._DIRECTION_
        rx_period = rx_period if rx_period is not None else self._PERIOD_
        tx_period = tx_period if tx_period is not None else self._PERIOD_
        tolerance = rx_tolerance if rx_tolerance is not None else self._RX_TOLERANCE_
        self.rx_state = RxState(rx_period, tolerance) if Direction.RX in self.direction else None
        self.tx_state = TxState(tx_period) if Direction.TX in self.direction else None

        if self._LENGTH_FIELD_NAME_ is not None:
            self._update_length()
        if self._CHECKSUM_FIELD_NAME_ is not None:
            self._update_checksum()

        self._signature_id: Optional[int] = None
        if self._signature is not None:
            self._signature.bind(type(self))            # layout burada hazır
            self._signature_id = self._signature.compute(bytes(self))

        self._registry.add(self)

    # ---------------------------------------------------------------- proje

    @classmethod
    def families(cls, channel: Optional[Channel] = None) -> list[Registry]:
        """Projenin aile registry'leri; channel verilirse o channel'dan RX alanlar."""
        if channel is None:
            return list(cls._families)
        return [reg for reg in cls._families if channel in reg.channels]

    @classmethod
    def lookup(cls, channel: Channel, raw: bytes) -> Optional[BaseMessageStructure]:
        """Ham paketin bu projede hangi mesaj nesnesine ait olduğunu bulur."""
        for reg in cls.families(channel):
            msg = reg.lookup(channel, raw)
            if msg is not None:
                return msg
        return None

    @classmethod
    def clear_registry(cls) -> None:
        """Projenin tüm kayıtlarını temizler (testler arası)."""
        for reg in cls._families:
            reg.clear()

    # ---------------------------------------------------------------- RX tarafı

    @property
    def signature_id(self) -> Optional[int]:
        return self._signature_id

    def validate(self, raw: bytes) -> bool:
        """Gelen paketin boyu, length alanı ve checksum'ı tutuyor mu?"""
        size = ctypes.sizeof(self)
        if len(raw) < size:
            return False
        if self._LENGTH_FIELD_NAME_ is not None:
            if self._read_field(raw, self._LENGTH_FIELD_NAME_).val != size:
                return False
        if self._CHECKSUM_FIELD_NAME_ is not None:
            field = self._read_field(raw, self._CHECKSUM_FIELD_NAME_)
            offset = getattr(type(self), self._CHECKSUM_FIELD_NAME_).offset
            if field.val != field.compute(raw[:offset]):
                return False
        return True

    def decode(self, raw: bytes) -> bool:
        """Paket geçerliyse nesnenin ctypes buffer'ına yerinde yazar."""
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
            getattr(self, self._COUNTER_FIELD_NAME_).next()
        if self._CHECKSUM_FIELD_NAME_ is not None:
            self._update_checksum()
        if self.tx_state is not None:
            self.tx_state.on_send()
        return bytes(self)

    # ---------------------------------------------------------------- yardımcılar

    def _read_field(self, raw: bytes, name: str):
        """Ham paketteki bir alanı kendi tipiyle okur."""
        ftype = find_field_type(type(self), name)
        return ftype.from_buffer_copy(raw, getattr(type(self), name).offset)

    def _update_length(self) -> None:
        getattr(self, self._LENGTH_FIELD_NAME_).val = ctypes.sizeof(self)

    def _update_checksum(self) -> None:
        offset = getattr(type(self), self._CHECKSUM_FIELD_NAME_).offset
        field = getattr(self, self._CHECKSUM_FIELD_NAME_)
        field.val = field.compute(bytes(self)[:offset])
