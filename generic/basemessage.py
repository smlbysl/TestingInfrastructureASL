from __future__ import annotations

import ctypes
from ctypes import Structure
from typing import Callable, ClassVar, Optional

from generic.channel import Channel
from generic.enumerations import Direction
from generic.fieldtypes import FieldType
from generic.registry import Registry
from generic.signature import Signature
from generic.state import RxState, TxState
from generic.timing import Timing

Callout = Callable[["BaseMessageStructure"], None]


class BaseMessageStructure(Structure):
    """Tüm mesajların tabanı.

    Hiyerarşi:  BaseMessageStructure -> Proje -> Aile -> mesaj sınıfı -> nesne
    - Proje: BaseMessageStructure'dan DOĞRUDAN türeyen sınıf. Endian (ctypes tabanı), header
      alanları, varsayılan channel/yön/zamanlama. Ailelerinin listesini (_families) tutar.
    - Aile: kendi _signature'ını tanımlayan sınıf. Kendi Registry'sini açar.
      Projenin kendisi de bir registry açar (signature'ı yoksa signature'sız mesajlar için).
    - Mesaj sınıfı: _fields_ ile payload.
    - Nesne: channel, yön, zamanlama nesne başına verilir (verilmezse sınıf varsayılanı).

    İsimlendirme: _x_ sadece ctypes'a ait (_fields_, _pack_); sınıf ayarları _x;
    dışarıya açık bilgiler property (channel, direction, signature_id, rx_state, tx_state).
    """
    _pack_ = 1

    # Özel alanlar: (_order, alan adı), _fields_ içindeki FieldType'lardan otomatik toplanır
    _special: ClassVar[list[tuple[int, str]]] = []

    # Proje / aile
    _signature: ClassVar[Optional[Signature]] = None
    _families: ClassVar[list[Registry]]          # projede tanımlanır
    _registry: ClassVar[Registry]                # projede ya da ailede tanımlanır

    # Varsayılanlar (nesne başına ezilebilir)
    _channel: ClassVar[Optional[Channel]] = None
    _direction: ClassVar[Direction] = Direction.RX
    _timing: ClassVar[Timing] = Timing()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        own = [(ftype._order, name) for name, ftype, *_ in cls.__dict__.get("_fields_", [])
               if isinstance(ftype, type) and issubclass(ftype, FieldType)]
        cls._special = sorted(cls._special + own)       # miras alınanlar + kendi alanları

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
                 rx: Optional[Timing] = None,
                 tx: Optional[Timing] = None,
                 **kw):
        # Metadata keyword olarak alınır, ctypes alanları super()'e gider
        super().__init__(*args, **kw)

        # Nesne bilgileri alt çizgili tutulur: ICD'de aynı isimde bir alan olsa da çakışmaz
        self._channel = channel if channel is not None else type(self)._channel
        if self._channel is None:
            raise AttributeError(f"{type(self).__name__}: channel yok "
                                 f"(channel= verin ya da sınıfta _channel tanımlayın)")
        self._direction = direction if direction is not None else type(self)._direction
        self._rx = RxState(rx or self._timing) if Direction.RX in self._direction else None
        self._tx = TxState(tx or self._timing) if Direction.TX in self._direction else None
        self._on_receive: list[Callout] = []
        self._on_send: list[Callout] = []

        for field in self._special_fields():
            field.on_init(self)

        self._signature_id: Optional[int] = None
        if self._signature is not None:
            self._signature.bind(type(self))            # layout burada hazır
            self._signature_id = self._signature.compute(bytes(self))

        self._registry.add(self)

    # ---------------------------------------------------------------- dışarıya açık bilgiler

    @property
    def channel(self) -> Channel:
        return self._channel

    @property
    def direction(self) -> Direction:
        return self._direction

    @property
    def signature_id(self) -> Optional[int]:
        return self._signature_id

    @property
    def rx_state(self) -> Optional[RxState]:
        return self._rx

    @property
    def tx_state(self) -> Optional[TxState]:
        return self._tx

    # ---------------------------------------------------------------- kullanıcı callout'ları

    def on_receive(self, callout: Callout) -> Callout:
        """Geçerli paket nesneye yazıldıktan sonra çağrılır. Dekoratör olarak da kullanılabilir."""
        self._on_receive.append(callout)
        return callout

    def on_send(self, callout: Callout) -> Callout:
        """pack() sırasında, counter/checksum'dan ÖNCE çağrılır (değişiklikler checksum'a girer)."""
        self._on_send.append(callout)
        return callout

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

    def validate(self, raw: bytes) -> bool:
        """Gelen paketin boyu ve özel alanları (length, checksum ...) tutuyor mu?"""
        if len(raw) < ctypes.sizeof(self):
            return False
        return all(field.on_receive(self, raw) for field in self._special_fields())

    def decode(self, raw: bytes) -> bool:
        """Paket geçerliyse nesnenin ctypes buffer'ına yerinde yazar."""
        if not self.validate(raw):
            if self._rx is not None:
                self._rx.on_error()
            return False
        ctypes.memmove(ctypes.addressof(self), raw, ctypes.sizeof(self))
        if self._rx is not None:
            self._rx.on_receive()
        for callout in self._on_receive:
            callout(self)
        return True

    # ---------------------------------------------------------------- TX tarafı

    def pack(self) -> bytes:
        """Gönderim için: kullanıcı callout'ları -> özel alanlar (counter, checksum) -> byte'lar."""
        for callout in self._on_send:
            callout(self)
        for field in self._special_fields():
            field.on_send(self)
        if self._tx is not None:
            self._tx.on_send()
        return bytes(self)

    # ---------------------------------------------------------------- yardımcılar

    def _special_fields(self) -> list[FieldType]:
        """Özel alanların bu nesnedeki görünümleri, _order sırasıyla (buffer'ı paylaşır)."""
        return [getattr(self, name) for _, name in self._special]
