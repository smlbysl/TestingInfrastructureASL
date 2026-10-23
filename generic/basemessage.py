from __future__ import annotations

import ctypes
from ctypes import Structure, sizeof
from typing import Optional

from generic.enumerations import ProtocolType, Direction
from generic.signature import SignatureClass, field_bits, _find_field_type


class BaseFooter(Structure):
    _crc_: Optional[str] = None

    def compute(self, data: bytes) -> int:
        raise NotImplementedError


class SignatureFilter():
    # Eski imza yapısı. Artık SignatureClass kullanılıyor; geriye uyumluluk için duruyor.
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
    _pack_ = 1

    _COUNTER_FIELD_NAME_ = None
    _LENGTH_FIELD_NAME_ = None
    _CHECKSUM_FIELD_NAME_ = None

    #Signature Fields
    _signature: Optional[SignatureClass] = None
    _registry: dict = {}          # {SignatureClass: {signature_id: mesaj sınıfı}}

    #Communicatin Fields
    _COMMPROTOCOL_: Optional[ProtocolType] = None
    _COMMINTERFACE_ = None

    #Message Data
    _DIRECTION_ = None
    _PERIOD_ = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name, ftype, *_ in cls.__dict__.get("_fields_", []):
            if isinstance(ftype, type) and issubclass(ftype, CounterType):  cls._COUNTER_FIELD_NAME_  = name
            if isinstance(ftype, type) and issubclass(ftype, LengthType):   cls._LENGTH_FIELD_NAME_   = name
            if isinstance(ftype, type) and issubclass(ftype, ChecksumType): cls._CHECKSUM_FIELD_NAME_ = name
        sig = cls.__dict__.get("_signature")
        if sig is not None:
            BaseMessageStructure._registry.setdefault(sig, {})

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.__post_init__()

    def __post_init__(self):
        self.__processsignature__()
        self.__processlength__()
        self.__processchecksum__()
        self.__processinterface__()

    @property
    def signature_id(self):
        return getattr(self, "_signature_id", None)

    @classmethod
    def Lookup(cls, raw: bytes) -> Optional[type[BaseMessageStructure]]:
        """Ham veriden imzaya bakarak mesaj sınıfını bulur."""
        if cls._signature is None or cls._signature.mask is None:
            return None
        sid = cls._signature.compute(raw)
        return BaseMessageStructure._registry[cls._signature].get(sid)

    def decode(self, raw: bytes) -> bool:
        size = ctypes.sizeof(self)
        if len(raw) < size:
            return False
        ctypes.memmove(ctypes.addressof(self), raw, size)
        return True

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

    def _pack(self) -> bytes:
        self._next_counter()
        self._update_checksum()
        return bytes(self)

    def _get_field_info(self, fieldname: str) -> dict:
        try:
            ftype = _find_field_type(type(self), fieldname)
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
        self._signature.bind(type(self))
        self._signature_id = self._signature.compute(bytes(self))

        table = BaseMessageStructure._registry.setdefault(self._signature, {})
        owner = table.get(self._signature_id)
        if owner is not None and owner is not type(self):
            raise ValueError(
                f"{type(self).__name__}: imza 0x{self._signature_id:X} zaten "
                f"{owner.__name__} için kayıtlı")
        table[self._signature_id] = type(self)

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
        if (self._COMMPROTOCOL_ is not None) and (self._COMMINTERFACE_ is not None):
            return True
        raise AttributeError(f"{type(self).__name__}: _COMMPROTOCOL_ / _COMMINTERFACE_ tanımlı değil")

    def SetProtocolInterface(self, protocol: Optional[ProtocolType], interface: Optional[int]):
        self._COMMPROTOCOL_ = protocol
        self._COMMINTERFACE_ = interface

    def GetProtocolInterface(self):
        return self._COMMPROTOCOL_, self._COMMINTERFACE_
