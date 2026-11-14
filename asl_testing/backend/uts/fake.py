"""FakeUtsApi and FakeUtsBackend: UTS stand-in that keeps the UTS JSON, for tests of the UTS format."""

__author__ = "İsmail Baysal"

import threading
import time
from collections import defaultdict
from typing import Optional

from asl_testing.backend.base import Response
from asl_testing.backend.uts.api import FilterGroups, UtsApi
from asl_testing.backend.uts.backend import UtsBackend


class FakeUtsApi(UtsApi):
    """post() records the request; put() adds an item as UTS would return it; get() drains the items.

    Configs and filters are only stored; the filter is not applied.
    """

    def __init__(self):
        self.posted: list[tuple[str, int, dict]] = []                  # (path, interface, body)
        self._items: dict[tuple[str, int], list[dict]] = defaultdict(list)
        self._lock = threading.Lock()         # put (test thread) vs get (RX thread)
        self.configs: dict[tuple[str, int], dict] = defaultdict(dict)
        self.filters: dict[tuple[str, int], tuple[str, FilterGroups]] = {}

    def post(self, path: str, interface: int, body: dict, timeout: float = 0.0) -> Response:
        self.posted.append((path, interface, dict(body)))
        return Response(ok=True, status=200)

    def get(self, path: str, interface: int, timeout: float = 0.0) -> Response:
        with self._lock:
            return Response(ok=True, status=200, data=self._items.pop((path, interface), []))

    def put(self, path: str, interface: int, item: dict) -> None:
        """Adds one item to the receive buffer of an interface."""
        with self._lock:
            self._items[(path, interface)].append(item)

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


class FakeUtsBackend(UtsBackend):
    """UtsBackend on a FakeUtsApi: what is sent and received passes through the real codecs."""

    def __init__(self, time_unit: float = 1.0):
        super().__init__(FakeUtsApi(), time_unit)

    @property
    def posted(self) -> list[tuple[str, int, dict]]:
        return self.api.posted

    def inject(self, channel, data: bytes, timestamp: Optional[float] = None) -> None:
        """The device sent data (bytes on the line) on the channel's interface."""
        stamp = time.time() if timestamp is None else timestamp
        codec = self.codec(channel)
        self.api.put(codec.path, channel.interface, codec.simulate(channel, bytes(data), stamp))
