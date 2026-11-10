"""FakeUtsClient: stands in for UTS during development and tests."""
import threading
import time
from collections import defaultdict
from typing import Optional

from asl_testing.protocol.pdu import Pci, Pdu
from asl_testing.uts.adapters import default_adapter
from asl_testing.uts.client import FilterGroups, UtsClient


class FakeUtsClient(UtsClient):
    """Stand-in for UTS: same JSON in and out, buffers in memory.

    post() records what is sent (path, interface, body). The device side puts items into the receive
    buffers, get() drains them like UTS:
        uts.device_sends(msg)                    # a message object, as the device would send it
        uts.device_sends_bytes(channel, data)    # SDU bytes on a channel (header added), e.g. broken ones
        uts.inject("ethernet", 1, {"message": [...]})   # a raw UTS item
    Items are stamped with time.time() in UTS units (the default adapter of the protocol).
    Configs and filters are only stored (the filter is not applied to injected items).
    """

    def __init__(self, time_unit: float = 1.0):
        self.time_unit = time_unit
        self.sent: list[tuple[str, int, dict]] = []
        self._buffers: dict[tuple[str, int], list[dict]] = defaultdict(list)
        self._lock = threading.Lock()         # the device side (test thread) and get (RX poller) share the buffers
        self.configs: dict[tuple[str, int], dict] = defaultdict(dict)
        self.filters: dict[tuple[str, int], tuple[str, FilterGroups]] = {}

    def post(self, path: str, interface: int, body: dict) -> None:
        self.sent.append((path, interface, dict(body)))

    def get(self, path: str, interface: int) -> list[dict]:
        with self._lock:
            return self._buffers.pop((path, interface), [])

    # ---------------------------------------------------------------- device side

    def inject(self, path: str, interface: int, item: dict) -> None:
        """Puts a raw UTS item into the receive buffer (stamped now if it has no timestamp)."""
        item = dict(item)
        item.setdefault("timestamp", time.time() / self.time_unit)
        with self._lock:
            self._buffers[(path, interface)].append(item)

    def device_sends(self, msg, timestamp: Optional[float] = None) -> dict:
        """The device sends msg (a message object, usually created with direction=TX): its packed bytes,
        with its PCI, on its channel. Returns the UTS item."""
        return self.device_sends_bytes(msg.channel, msg.pack(), msg.pci, timestamp)

    def device_sends_bytes(self, channel, data: bytes, pci: Optional[Pci] = None,
                           timestamp: Optional[float] = None) -> dict:
        """The device sends an SDU on a channel (the protocol adds its header / PCI). Returns the UTS item."""
        protocol = channel.protocol
        pci = pci if pci is not None else protocol.make_pci()
        item = default_adapter(protocol, self.time_unit).to_uts(protocol, Pdu(pci, bytes(data)))
        if timestamp is not None:
            item["timestamp"] = timestamp / self.time_unit
        self.inject(protocol.path, channel.interface, item)
        return item

    # ---------------------------------------------------------------- management

    def get_config(self, path: str, interface: int) -> dict:
        return dict(self.configs[(path, interface)])

    def set_config(self, path: str, interface: int, settings: dict) -> None:
        self.configs[(path, interface)].update(settings)

    def get_filter(self, path: str, interface: int) -> tuple[str, FilterGroups]:
        kind, groups = self.filters.get((path, interface), ("NONE", []))
        return kind, [list(g) for g in groups]

    def set_filter(self, path: str, interface: int, kind: str, groups: FilterGroups) -> None:
        self.filters[(path, interface)] = (kind, [list(g) for g in groups])
