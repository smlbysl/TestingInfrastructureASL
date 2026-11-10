"""Channel: one line of a bus = protocol + gateway adapter + interface + the messages registered on it.

Messages register on their channel, so a channel only ever matches its own messages.
Identification of an incoming PDU (in this order):
  1. PCI: the messages registered under pdu.pci.key() (plain RS422/Ethernet: all of them share one key)
  2. signature: if the candidates define one, the one whose signature matches the SDU
  3. a single candidate without a signature takes every PDU of its key
  4. otherwise: unknown
The rules are checked when a message registers, so an ambiguity fails at definition time, not at run time.
"""
from typing import Optional

from .adapters import UtsAdapter, adapter_for
from .pdu import Pdu
from .protocols import Protocol


class Channel:
    def __init__(self, name: str, interface: int, protocol: Protocol, adapter: Optional[UtsAdapter] = None):
        self.name = name
        self.interface = interface
        self.protocol = protocol
        self.adapter = adapter or adapter_for(protocol)
        self.registry: dict[tuple, list] = {}          # pci key -> RX messages

    @property
    def address(self) -> tuple[str, int]:
        """Where the gateway reads and writes this channel; several channels may share one."""
        return self.protocol.path, self.interface

    def __repr__(self) -> str:
        return self.name

    # ---------------------------------------------------------------- registry

    def register(self, msg) -> None:
        key = msg.pci.key()
        entries = self.registry.setdefault(key, [])
        for i, other in enumerate(entries):
            if type(other) is type(msg) and other.signature() == msg.signature():
                entries[i] = msg                        # the same message created again replaces the old one
                return
        if msg.signature() is None and entries:
            raise ValueError(f"{self.name} {key}: {type(msg).__name__} has no signature, "
                             f"but {type(entries[0]).__name__} is already registered there")
        if any(other.signature() is None for other in entries):
            raise ValueError(f"{self.name} {key}: {type(entries[0]).__name__} takes every packet of this "
                             f"address (no signature); {type(msg).__name__} needs it to have one")
        if any(other.signature() == msg.signature() for other in entries):
            raise ValueError(f"{self.name} {key}: signature {msg.signature()} is used twice")
        entries.append(msg)

    def identify(self, pdu: Pdu):
        entries = self.registry.get(pdu.pci.key())
        if not entries:
            return None
        if len(entries) == 1 and entries[0].signature() is None:
            return entries[0]
        for msg in entries:
            if msg.matches(pdu.sdu):
                return msg
        return None
