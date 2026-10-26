"""Registry: bir mesaj ailesine (aynı signature'ı paylaşan mesajlar) ait kayıtlar.

Aile sınıfı tanımlandığında kendi Registry'sini açar ve projesinin aile listesine ekler.
Mesaj nesnesi kayıt kurallarını bilmez; sadece registry.add(self) çağırır.
Registry nesnelerin referansını tutar; decode gelen veriyi doğrudan bu nesnelere yazar.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from generic.channel import Channel
from generic.signature import Signature

if TYPE_CHECKING:
    from generic.basemessage import BaseMessageStructure


class Registry:
    def __init__(self, signature: Optional[Signature]):
        self.signature = signature
        self.all: list[BaseMessageStructure] = []               # tek kaynak: tüm nesneler
        self.dispatch: dict[tuple[Channel, int], BaseMessageStructure] = {}  # sadece RX içerenler
        self.channels: set[Channel] = set()                     # bu ailenin RX aldığı channel'lar
        self.periodic_rx: list[BaseMessageStructure] = []       # monitor için
        self.periodic_tx: list[BaseMessageStructure] = []       # scheduler için

    def add(self, msg: BaseMessageStructure) -> None:
        self.all.append(msg)
        if msg._rx is not None:
            if msg._signature_id is not None:
                key = (msg._channel, msg._signature_id)
                owner = self.dispatch.get(key)
                if owner is not None:
                    raise ValueError(
                        f"Çakışma: {type(msg).__name__} ve {type(owner).__name__} aynı "
                        f"channel ({msg._channel}) ve imzaya (0x{msg._signature_id:X}) sahip")
                self.dispatch[key] = msg
                self.channels.add(msg._channel)
            if msg._rx.timing.is_periodic:
                self.periodic_rx.append(msg)
        # TX-only nesneler dispatch'e girmez: gelen paket TX nesnesinin üzerine yazmasın
        if msg._tx is not None and msg._tx.timing.is_periodic:
            self.periodic_tx.append(msg)

    def lookup(self, channel: Channel, raw: bytes) -> Optional[BaseMessageStructure]:
        """Ham paketten bu ailedeki mesaj nesnesini bulur."""
        if self.signature is None or self.signature.mask is None:
            return None
        return self.dispatch.get((channel, self.signature.compute(raw)))

    def clear(self) -> None:
        """Testler arasında temizlik için."""
        self.all.clear()
        self.dispatch.clear()
        self.channels.clear()
        self.periodic_rx.clear()
        self.periodic_tx.clear()
