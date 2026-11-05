"""Link: a physical UTS interface (ethernet/<n> or serials/<n>).

Links are defined in the setup file, not in code:

    [links.ETH1]
    bus = "ethernet"
    interface = 1
    buffer_size = 10

config_mode:
- "auto"   : the settings are written to UTS when Comm opens
- "manual" : UTS keeps its current settings; they are read and copied into the link
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, Optional

from generic.framing import Splitter

CONFIG_MODES = ("auto", "manual")


@dataclass(eq=False)
class Link:
    name: str
    interface: int
    config_mode: str = "auto"
    splitter: Splitter = field(default_factory=Splitter)
    # settings common to all UTS interfaces
    max_message_size: int = 1024
    buffer_size: int = 10
    overwrite_enabled: bool = True
    start_of_header: Optional[list[int]] = None
    timeout_ms: int = 10

    bus: ClassVar[str]                              # path segment in the UTS URL
    _uts_keys: ClassVar[dict[str, str]] = {         # field name -> UTS JSON key
        "max_message_size": "maxMessageSize",
        "buffer_size": "bufferSize",
        "overwrite_enabled": "overwriteEnabled",
        "start_of_header": "startOfHeader",
        "timeout_ms": "timeoutAsMs",
    }

    def __post_init__(self):
        if self.config_mode not in CONFIG_MODES:
            raise ValueError(f"link {self.name}: config_mode must be one of {CONFIG_MODES}")
        self.given: set[str] = set()                # settings written in the setup file

    @classmethod
    def from_config(cls, name: str, section: dict[str, Any], default_mode: str) -> "Link":
        values = dict(section)
        bus = values.pop("bus", None)
        if bus not in LINK_TYPES:
            raise ValueError(f"link {name}: bus must be one of {', '.join(LINK_TYPES)}, not {bus!r}")
        link_cls = LINK_TYPES[bus]
        splitter = values.pop("splitter", None)
        known = {f.name for f in fields(link_cls)} - {"name", "splitter"}
        unknown = set(values) - known
        if unknown:
            raise ValueError(f"link {name}: unknown settings {', '.join(sorted(unknown))}")
        values.setdefault("config_mode", default_mode)
        link = link_cls(name=name, **values)
        if splitter is not None:
            link.splitter = _load_object(splitter)()
        link.given = set(values) - {"interface", "config_mode"}
        return link

    def uts_keys(self) -> dict[str, str]:
        keys = dict(Link._uts_keys)
        keys.update(type(self)._uts_keys)
        return keys

    def to_uts(self) -> dict[str, Any]:
        """Settings as the UTS configs body."""
        return {key: getattr(self, attr) for attr, key in self.uts_keys().items()}

    def apply_uts(self, config: dict[str, Any]) -> list[str]:
        """Copies settings read from UTS into the link.

        Returns a line for every setting written in the setup file that differs from UTS.
        """
        differences = []
        for attr, key in self.uts_keys().items():
            if key not in config:
                continue
            if attr in self.given and getattr(self, attr) != config[key]:
                differences.append(f"{attr}: setup {getattr(self, attr)!r}, UTS {config[key]!r}")
            setattr(self, attr, config[key])
        return differences

    def __str__(self) -> str:
        return f"{self.name} ({self.bus}/{self.interface})"


@dataclass(eq=False)
class EthernetLink(Link):
    interface_type: str = "UDP"

    bus = "ethernet"
    _uts_keys = {"interface_type": "interfaceType"}


@dataclass(eq=False)
class SerialLink(Link):
    buffer_size: int = 1000
    overwrite_enabled: bool = False
    start_of_header: Optional[list[int]] = field(default_factory=list)
    timeout_ms: int = 200
    serial_interface_type: str = "RS-422"
    baud_rate: int = 921600
    data_bits: str = "8"
    stop_bits: str = "1"
    parity: str = "NONE"
    flow_control: str = "NONE"

    bus = "serials"
    _uts_keys = {
        "serial_interface_type": "serialInterfaceType",
        "baud_rate": "baudRate",
        "data_bits": "dataBits",
        "stop_bits": "stopBits",
        "parity": "parity",
        "flow_control": "flowControl",
    }


LINK_TYPES: dict[str, type[Link]] = {"ethernet": EthernetLink, "serials": SerialLink}


def _load_object(path: str):
    """'package.module:Name' -> the object."""
    module, _, name = path.partition(":")
    return getattr(importlib.import_module(module), name)
