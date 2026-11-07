"""Signals: the fields of a message class as flat paths, and their values in a message image.

A path names one value:  "speed", "comut[0]", "cmd.startReq", "messageLength".
- plain fields and bit fields         -> their value
- arrays                              -> one path per element; char arrays -> one text value
- special field types with a `value`  -> the field's .val (e.g. a counter, a length)
- other structures (e.g. CmdByte)     -> one path per sub-field
Only numbers can be plotted; text values are shown in the tree only.
"""
import ctypes
from typing import Any, Callable

from asl_testing.message.fields import FieldType

Getter = Callable[[Any], Any]


def fields_in_order(cls) -> list[tuple]:
    """_fields_ of a ctypes structure including its bases, in layout order."""
    out = []
    for klass in reversed(cls.__mro__):
        out.extend(klass.__dict__.get("_fields_", []))
    return out


def signal_paths(cls) -> list[tuple[str, Getter]]:
    """(path, getter) for every value of a message class; getter(message object) -> value."""
    out: list[tuple[str, Getter]] = []
    _walk(cls, "", lambda m: m, out)
    return out


def _walk(cls, prefix: str, parent: Getter, out: list) -> None:
    for name, ftype, *_ in fields_in_order(cls):
        path = f"{prefix}{name}"
        get = (lambda p, n: lambda m: getattr(p(m), n))(parent, name)
        if isinstance(ftype, type) and issubclass(ftype, ctypes.Array):
            if ftype._type_ is ctypes.c_char:
                out.append((path, (lambda g: lambda m: g(m).decode("ascii", "replace"))(get)))
            else:
                for i in range(ftype._length_):
                    out.append((f"{path}[{i}]", (lambda g, i: lambda m: g(m)[i])(get, i)))
        elif isinstance(ftype, type) and issubclass(ftype, ctypes.Structure):
            names = [f[0] for f in fields_in_order(ftype)]
            if issubclass(ftype, FieldType) and names == ["value"]:
                out.append((path, (lambda g: lambda m: g(m).val)(get)))
            else:
                _walk(ftype, f"{path}.", get, out)
        else:
            out.append((path, get))


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
