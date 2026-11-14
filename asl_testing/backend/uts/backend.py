"""UtsBackend: carries the bytes of a channel through UTS.

    send      codec.encode -> api.post     one POST at a time per interface
    receive   api.get -> codec.decode of every item

The codec is chosen by the bus of the channel; the requests are made by a UtsApi.
Every request has a timeout (the codec's, or the one given here), its duration is measured, and the
result is logged on the logger "asl_testing.uts":

    failed request            ERROR
    successful POST           DEBUG
    GET that returned items   DEBUG      (an empty GET is not logged)

A request is not repeated. An exception of the api becomes a failed Response.
"""

__author__ = "İsmail Baysal"

import logging
import threading
import time
from dataclasses import replace
from typing import Optional

from asl_testing.backend.base import Backend, Response
from asl_testing.backend.uts.api import UtsApi
from asl_testing.backend.uts.codecs import Codec, EthernetCodec, Mil1553Codec, SerialCodec
from asl_testing.backend.uts.control import UtsControl

LOG = "asl_testing.uts"


class UtsBackend(Backend):
    def __init__(self, api: UtsApi, time_unit: float = 1.0, timeout: Optional[float] = None, log=None):
        self.api = api
        self.timeout = timeout                  # seconds for every request; None: the codec's timeout
        self.log = log or logging.getLogger(LOG)
        self.codecs: dict[str, Codec] = {
            "serial": SerialCodec(time_unit),
            "ethernet": EthernetCodec(time_unit),
            "mil1553": Mil1553Codec(time_unit),
        }
        self.control = UtsControl(self, log=log)
        # UTS may overwrite a message whose POST has not been answered yet
        self._tx_locks: dict[tuple[str, int], threading.Lock] = {}
        self._guard = threading.Lock()

    def codec(self, channel) -> Codec:
        try:
            return self.codecs[channel.bus]
        except KeyError:
            raise ValueError(f"UTS has no codec for the bus {channel.bus!r} of {channel}") from None

    def send(self, channel, data: bytes) -> Response:
        codec = self.codec(channel)
        body = codec.encode(channel, data)
        with self._tx_lock(codec.path, channel.interface):
            response = self._request("POST", codec, channel, body)
        if response.ok:
            self.log.debug("POST /%s/%d ok (%.3f s), UTS time %s", codec.path, channel.interface,
                           response.elapsed, response.timestamp)
        return response

    def receive(self, channel) -> Response:
        codec = self.codec(channel)
        response = self._request("GET", codec, channel)
        if not response.ok:
            return response
        items = response.data or []
        if items:
            self.log.debug("GET /%s/%d ok (%.3f s), %d item(s)", codec.path, channel.interface,
                           response.elapsed, len(items))
        return replace(response, data=[codec.decode(channel, item) for item in items])

    def _request(self, method: str, codec: Codec, channel, body: Optional[dict] = None) -> Response:
        timeout = codec.timeout if self.timeout is None else self.timeout
        started = time.monotonic()
        try:
            if method == "POST":
                response = self.api.post(codec.path, channel.interface, body, timeout)
            else:
                response = self.api.get(codec.path, channel.interface, timeout)
        except Exception as error:
            response = Response(ok=False, message=f"{type(error).__name__}: {error}")
        response = replace(response, elapsed=time.monotonic() - started)
        if not response.ok:
            self.log.error("%s /%s/%d failed: status %s, code %s, %s (%.3f s)", method, codec.path,
                           channel.interface, response.status, response.code, response.message, response.elapsed)
        return response

    def _tx_lock(self, path: str, interface: int) -> threading.Lock:
        with self._guard:
            return self._tx_locks.setdefault((path, interface), threading.Lock())
