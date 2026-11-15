"""UtsAdapter: the adapter of UTS (UTS is an HTTP service); everything of UTS in one class.

    message flow    send(channel, wire), receive(channel)                     used by the transport
    config, filter  get_config, set_config, get_filter, set_filter,           used by the test:
                    clear_filter, add_filter(msg), remove_filter(msg)         comm.adapter.add_filter(status)
    UTS requests    post, get, read_config, write_config, read_filter,        to be written for the real UTS
                    write_filter

The adapter holds the protocol definitions (protocols.py). A channel names its protocol; the adapter
finds the definition and uses it:

    send(channel, wire)     protocol.encode -> post(path, interface, body, timeout) -> time of the send
    receive(channel)        get(path, interface, timeout) -> protocol.decode of every item, overflow flag

post and get return the JSON body of the answer of UTS. For an answer that is not 200, the adapter for
the real UTS raises answer(status, body), which reads statusInfo into an AdapterError:

    def post(self, path, interface, body, timeout):
        status, answer = self.wrapper.....              # the existing module
        return self.answer(status, answer)

POST sends on an interface; GET returns what was received there and empties the buffer. An adapter for
the real UTS subclasses UtsAdapter, calls super().__init__() and writes post and get (the config and
filter requests when they are needed; until then they raise NotImplementedError). A request that is not
answered within timeout seconds is given up and raises AdapterError; it is not repeated. The timeout comes
from the protocol definition (Ethernet and 1553: 2 s, RS422: 3 s), or from UtsAdapter(timeout=...).

send() makes one POST at a time per interface: UTS may overwrite a message whose POST has not been
answered yet. Different interfaces do not wait for each other. GET takes no lock (one RX thread per
channel). Config and filter calls are synchronous, independent of the RX / TX threads, logged as INFO.

Open until the UTS API is available: body of config and filter calls
(master: {"type": kind, "filter": [[{"filterBytePos", "filterValue"}]]}).
"""

__author__ = "İsmail Baysal"

import logging
import threading
from abc import abstractmethod
from typing import Any, Optional, Union

from asl_testing.adapter.base import Adapter, AdapterError, FilterGroups, Polled
from asl_testing.adapter.uts.filters import signature_filter
from asl_testing.adapter.uts.protocols import EthernetProtocol, Mil1553Protocol, Protocol, Rs422Protocol
from asl_testing.channel.channel import Channel
from asl_testing.message.base import BaseMessageStructure

Target = Union[Channel, BaseMessageStructure]


class UtsAdapter(Adapter):
    def __init__(self, time_unit: float = 1e-6, timeout: Optional[float] = None, log=None):
        # protocol name (Channel.protocol) -> definition; time_unit: seconds per UTS time unit
        self.protocols: dict[str, Protocol] = {
            "ethernet": EthernetProtocol(time_unit),
            "rs422": Rs422Protocol(time_unit),
            "mil1553": Mil1553Protocol(time_unit),
        }
        self.timeout = timeout          # seconds for every request; None: the timeout of each protocol
        self.log = log or logging.getLogger(__name__)
        self._post_locks: dict[tuple[str, int], threading.Lock] = {}     # one per (path, interface)
        self._guard = threading.Lock()                                   # creating a lock in _post_locks

    def protocol(self, channel) -> Protocol:
        """Definition of the channel's protocol."""
        try:
            return self.protocols[channel.protocol]
        except KeyError:
            raise ValueError(f"UTS adapter has no protocol {channel.protocol!r} (channel {channel})") from None

    def timeout_of(self, protocol: Protocol) -> float:
        """Seconds a request of the protocol waits for an answer."""
        return protocol.timeout if self.timeout is None else self.timeout

    # ---------------------------------------------------------------- message flow

    def send(self, channel, wire: bytes) -> Optional[float]:
        """Sends the bytes on the line of a channel; returns the UTS time of the send in seconds (or None)."""
        protocol = self.protocol(channel)
        body = protocol.encode(channel, wire)
        with self._post_lock(protocol.path, channel.interface):
            answer = self.post(protocol.path, channel.interface, body, self.timeout_of(protocol))
        return protocol.sent_time(answer)

    def _post_lock(self, path: str, interface: int) -> threading.Lock:
        with self._guard:
            return self._post_locks.setdefault((path, interface), threading.Lock())

    def receive(self, channel) -> Polled:
        """What the channel's interface received since the last call."""
        protocol = self.protocol(channel)
        answer = self.get(protocol.path, channel.interface, self.timeout_of(protocol))
        return Polled([protocol.decode(channel, item) for item in protocol.items(answer)], protocol.overflow(answer))

    @staticmethod
    def answer(status: Optional[int], body: Optional[dict]) -> dict:
        """Body of a UTS answer; for a status other than 200, AdapterError with what statusInfo says."""
        if status == 200:
            return body or {}
        info = (body or {}).get("statusInfo") or {}
        raise AdapterError(f"UTS answered {status}: {info.get('status')} {info.get('message')}",
                           status=status, code=info.get("status"))

    # ---------------------------------------------------------------- config

    def get_config(self, target: Target) -> dict[str, Any]:
        path, interface = self._interface(target)
        return self.read_config(path, interface)

    def set_config(self, target: Target, **settings) -> None:
        path, interface = self._interface(target)
        self.write_config(path, interface, settings)
        self.log.info("%s: config %s", _channel(target), settings)

    # ---------------------------------------------------------------- filters

    def get_filter(self, target: Target) -> tuple[str, FilterGroups]:
        """(kind, groups) of the interface; kind "NONE" means no filter."""
        path, interface = self._interface(target)
        return self.read_filter(path, interface)

    def set_filter(self, target: Target, groups: FilterGroups, kind: str = "INCLUSIVE") -> None:
        """Writes the whole filter."""
        path, interface = self._interface(target)
        self.write_filter(path, interface, kind, groups)
        self.log.info("%s: filter %s %s", _channel(target), kind, groups)

    def clear_filter(self, target: Target) -> None:
        """Removes the filter; every packet passes."""
        path, interface = self._interface(target)
        self.write_filter(path, interface, "NONE", [])
        self.log.info("%s: filter cleared", _channel(target))

    def add_filter(self, msg: BaseMessageStructure) -> None:
        """Adds the message's signature bytes to the filter (read, add, write). Adding twice changes nothing."""
        path, interface = self._interface(msg)
        group = signature_filter(msg, msg.channel.framing.envelope.offset)
        kind, groups = self.read_filter(path, interface)
        if group in groups:
            return
        self.write_filter(path, interface, "INCLUSIVE", groups + [group])
        self.log.info("%s: filter + %s %s", msg.channel, type(msg).__name__, group)

    def remove_filter(self, msg: BaseMessageStructure) -> None:
        """Removes the message's group; with no group left the filter is removed."""
        path, interface = self._interface(msg)
        group = signature_filter(msg, msg.channel.framing.envelope.offset)
        kind, groups = self.read_filter(path, interface)
        if group not in groups:
            return
        groups = [g for g in groups if g != group]
        self.write_filter(path, interface, "INCLUSIVE" if groups else "NONE", groups)
        self.log.info("%s: filter - %s", msg.channel, type(msg).__name__)

    def _interface(self, target: Target) -> tuple[str, int]:
        ch = _channel(target)
        return self.protocol(ch).path, ch.interface

    # ---------------------------------------------------------------- UTS requests

    @abstractmethod
    def post(self, path: str, interface: int, body: dict, timeout: float) -> dict:
        """POST /{path}/{interface}/messages with the body from the protocol; returns the answer body.

        AdapterError for an error answer (see answer()) or no answer within timeout seconds.
        """

    @abstractmethod
    def get(self, path: str, interface: int, timeout: float) -> dict:
        """GET /{path}/{interface}/messages; returns the answer body ({"messages": [...], "isBufferOverflow": ...}).

        AdapterError for an error answer (see answer()) or no answer within timeout seconds.
        """

    def read_config(self, path: str, interface: int) -> dict:
        """Settings of an interface."""
        raise NotImplementedError(f"{type(self).__name__}.read_config")

    def write_config(self, path: str, interface: int, settings: dict) -> None:
        """Writes settings of an interface."""
        raise NotImplementedError(f"{type(self).__name__}.write_config")

    def read_filter(self, path: str, interface: int) -> tuple[str, FilterGroups]:
        """Receive filter as (kind, groups); kind "NONE" means no filter."""
        raise NotImplementedError(f"{type(self).__name__}.read_filter")

    def write_filter(self, path: str, interface: int, kind: str, groups: FilterGroups) -> None:
        """kind "INCLUSIVE": only the groups pass; "NONE": no filter."""
        raise NotImplementedError(f"{type(self).__name__}.write_filter")


def _channel(target: Target) -> Channel:
    return target if isinstance(target, Channel) else target.channel
