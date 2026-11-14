"""UtsBackend: carries the bytes of a channel through UTS.

    send      codec.encode -> api.post
    receive   api.get -> codec.decode of every item

The codec is chosen by the bus of the channel; the requests are made by a UtsApi.
"""

__author__ = "İsmail Baysal"

from dataclasses import replace

from asl_testing.backend.base import Backend, Response
from asl_testing.backend.uts.api import UtsApi
from asl_testing.backend.uts.codecs import Codec, EthernetCodec, Mil1553Codec, SerialCodec
from asl_testing.backend.uts.control import UtsControl


class UtsBackend(Backend):
    def __init__(self, api: UtsApi, time_unit: float = 1.0, log=None):
        self.api = api
        self.codecs: dict[str, Codec] = {
            "serial": SerialCodec(time_unit),
            "ethernet": EthernetCodec(time_unit),
            "mil1553": Mil1553Codec(time_unit),
        }
        self.control = UtsControl(self, log=log)

    def codec(self, channel) -> Codec:
        try:
            return self.codecs[channel.bus]
        except KeyError:
            raise ValueError(f"UTS has no codec for the bus {channel.bus!r} of {channel}") from None

    def send(self, channel, data: bytes) -> Response:
        codec = self.codec(channel)
        return self.api.post(codec.path, channel.interface, codec.encode(channel, data))

    def receive(self, channel) -> Response:
        codec = self.codec(channel)
        response = self.api.get(codec.path, channel.interface)
        if not response.ok:
            return response
        return replace(response, data=[codec.decode(channel, item) for item in response.data or []])
