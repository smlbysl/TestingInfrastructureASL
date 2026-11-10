"""A fake UTS and a minimal communication loop that walks the layers.

TX:  message -> SDU -> PDU (protocol adds the PCI) -> adapter -> UTS JSON -> POST
RX:  GET -> UTS JSON -> adapter -> PDU (the channel's protocol accepts it or not) -> channel registry -> message
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from .adapters import UtsFormatError
from .channel import Channel


class FakeUts:
    """Keeps POSTed bodies; the device side puts items into the receive buffers."""

    def __init__(self):
        self.sent: list[tuple[str, int, dict]] = []
        self.buffers: dict[tuple[str, int], list[dict]] = defaultdict(list)

    def post(self, path: str, interface: int, body: dict) -> None:
        self.sent.append((path, interface, body))

    def get(self, path: str, interface: int) -> list[dict]:
        items, self.buffers[(path, interface)] = self.buffers[(path, interface)], []
        return items

    def device_sends(self, path: str, interface: int, item: dict) -> None:
        self.buffers[(path, interface)].append(item)


@dataclass
class Result:
    kind: str                       # "received", "invalid", "unknown", "gateway error"
    channel: Optional[Channel]
    message: object = None
    detail: str = ""


class Gateway:
    def __init__(self, uts: FakeUts, channels: list[Channel]):
        self.uts = uts
        self.by_address: dict[tuple[str, int], list[Channel]] = defaultdict(list)
        for ch in channels:
            self.by_address[ch.address].append(ch)
        for group in self.by_address.values():          # channels with an in-band header first
            group.sort(key=lambda ch: getattr(ch.protocol, "header", None) is None)

    def send(self, msg) -> dict:
        ch = msg._channel
        pdu = msg.to_pdu()
        ch.protocol.check_sdu(pdu.sdu)
        body = ch.adapter.to_uts(ch.protocol, pdu)
        self.uts.post(ch.protocol.path, ch.interface, body)
        return body

    def poll(self) -> list[Result]:
        results = []
        for (path, interface), channels in self.by_address.items():
            for item in self.uts.get(path, interface):
                results.append(self._receive(item, channels))
        return results

    def _receive(self, item: dict, channels: list[Channel]) -> Result:
        for ch in channels:
            try:
                pdu = ch.adapter.from_uts(ch.protocol, item)
            except UtsFormatError as error:              # logged, the loop goes on
                return Result("gateway error", ch, detail=str(error))
            if pdu is None:
                continue                                 # not this channel's PCI: try the next one
            msg = ch.identify(pdu)
            if msg is None:
                return Result("unknown", ch, detail=f"pci={pdu.pci} sdu={pdu.sdu.hex(' ')}")
            if not msg.decode(pdu):
                return Result("invalid", ch, msg, detail=f"{len(pdu.sdu)} bytes")
            return Result("received", ch, msg)
        return Result("unknown", None, detail=f"no channel accepts {item}")
