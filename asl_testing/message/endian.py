"""Byte order of a project and its field types: endian="big" or endian="little" (default little).

The value is kept in one place in the project and given to every class that chooses it:

    # projects/<project>/settings.py
    ENDIAN = "big"

    class Counter8(CounterType, endian=ENDIAN): ...              # types.py
    class ProjectBase(BaseMessageStructure, endian=ENDIAN): ...  # project base

The metaclass adds BigEndianStructure / LittleEndianStructure to the bases. Subclasses keep the
byte order of their base. A message refuses a field type of the other byte order (ctypes would
keep the field's own order without a word).
"""

__author__ = "İsmail Baysal"

import sys
from ctypes import BigEndianStructure, LittleEndianStructure, Structure

_BASES = {"big": BigEndianStructure, "little": LittleEndianStructure}
_OTHER = "big" if sys.byteorder == "little" else "little"


class EndianMeta(type(Structure)):
    """Metaclass of BaseMessageStructure and FieldType."""

    def __new__(mcls, name, bases, ns, endian=None, **kwargs):
        if endian is not None:
            base = _BASES[endian]
            if not any(issubclass(b, base) for b in bases):
                bases += (base,)
            mcls = _META[endian]
        return super().__new__(mcls, name, bases, ns, **kwargs)

    def __init__(cls, name, bases, ns, endian=None, **kwargs):
        super().__init__(name, bases, ns, **kwargs)


class _SwappedMeta(EndianMeta, type(_BASES[_OTHER])):
    """Same, for the byte order that is not the machine's."""


_META = {sys.byteorder: EndianMeta, _OTHER: _SwappedMeta}


def byte_order(cls) -> str:
    """'big' or 'little'."""
    return _OTHER if hasattr(cls, "_swappedbytes_") else sys.byteorder
