"""UtsClient: how UTS is reached (UTS is an HTTP service).

The client holds the protocol definitions (protocols.py). A channel names its protocol; the client
finds the definition and uses it:

    send(channel, wire)     protocol.encode -> post(path, interface, body, timeout)
    receive(channel)        get(path, interface, timeout) -> protocol.decode of every item

post and get are the requests themselves: POST sends on an interface; GET returns what was received
there and empties the buffer. A client for the real UTS implements these two and calls
super().__init__(). A request that is not answered within timeout seconds is given up and raises
UtsError; it is not repeated. The timeout comes from the protocol definition (Ethernet and 1553: 2 s,
RS422: 3 s), or from UtsClient(timeout=...) for every protocol.

send() makes one POST at a time per interface: UTS may overwrite a message whose POST has not been
answered yet. Different interfaces do not wait for each other. GET takes no lock (one RX thread).

Open until the UTS API is available: JSON layout of GET, timestamp unit, body of config and filter
calls (master: {"type": kind, "filter": [[{"filterBytePos", "filterValue"}]]}).
"""

__author__ = "İsmail Baysal"

import threading
from abc import ABC, abstractmethod
from typing import Optional

from asl_testing.uts.protocols import EthernetProtocol, Mil1553Protocol, Protocol, Received, Rs422Protocol


class UtsError(Exception):
    """A UTS request failed (HTTP error, status not OK, UTS unreachable, no answer within the timeout)."""


FilterGroups = list[list[tuple[int, int]]]   # OR of groups; a group is an AND of (byte position, value)


class UtsClient(ABC):
    def __init__(self, time_unit: float = 1.0, timeout: Optional[float] = None):
        # protocol name (Channel.protocol) -> definition; time_unit: seconds per UTS time unit
        self.protocols: dict[str, Protocol] = {
            "ethernet": EthernetProtocol(time_unit),
            "rs422": Rs422Protocol(time_unit),
            "mil1553": Mil1553Protocol(time_unit),
        }
        self.timeout = timeout          # seconds for every request; None: the timeout of each protocol
        self._post_locks: dict[tuple[str, int], threading.Lock] = {}     # one per (path, interface)
        self._guard = threading.Lock()                                   # creating a lock in _post_locks

    def protocol(self, channel) -> Protocol:
        """Definition of the channel's protocol."""
        try:
            return self.protocols[channel.protocol]
        except KeyError:
            raise ValueError(f"UTS client has no protocol {channel.protocol!r} (channel {channel})") from None

    def timeout_of(self, protocol: Protocol) -> float:
        """Seconds a request of the protocol waits for an answer."""
        return protocol.timeout if self.timeout is None else self.timeout

    def send(self, channel, wire: bytes) -> None:
        """Sends the bytes on the line of a channel."""
        protocol = self.protocol(channel)
        body = protocol.encode(channel, wire)
        with self._post_lock(protocol.path, channel.interface):
            self.post(protocol.path, channel.interface, body, self.timeout_of(protocol))

    def _post_lock(self, path: str, interface: int) -> threading.Lock:
        with self._guard:
            return self._post_locks.setdefault((path, interface), threading.Lock())

    def receive(self, channel) -> list[Received]:
        """What the channel's interface received since the last call."""
        protocol = self.protocol(channel)
        items = self.get(protocol.path, channel.interface, self.timeout_of(protocol))
        return [protocol.decode(channel, item) for item in items]

    # ---------------------------------------------------------------- requests

    @abstractmethod
    def post(self, path: str, interface: int, body: dict, timeout: float) -> None:
        """POST /{path}/{interface}/messages with the body from the protocol; UtsError after timeout seconds."""

    @abstractmethod
    def get(self, path: str, interface: int, timeout: float) -> list[dict]:
        """GET /{path}/{interface}/messages: items received since the last call; UtsError after timeout seconds."""

    # ---------------------------------------------------------------- management (optional)

    def get_config(self, path: str, interface: int) -> dict:
        """Settings of an interface."""
        raise NotImplementedError

    def set_config(self, path: str, interface: int, settings: dict) -> None:
        """Writes settings of an interface."""
        raise NotImplementedError

    def get_filter(self, path: str, interface: int) -> tuple[str, FilterGroups]:
        """Receive filter as (kind, groups); kind "NONE" means no filter."""
        raise NotImplementedError

    def set_filter(self, path: str, interface: int, kind: str, groups: FilterGroups) -> None:
        """kind "INCLUSIVE": only the groups pass; "NONE": no filter."""
        raise NotImplementedError
