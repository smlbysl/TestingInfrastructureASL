"""ProjectRegistry: bir projeye ait mesaj nesnelerinin kayıtları.

BaseMessageStructure._registry[proje sınıfı] -> ProjectRegistry
Registry nesnelerin referansını tutar; decode gelen veriyi doğrudan bu nesnelere yazar.
"""
from dataclasses import dataclass, field


@dataclass
class ProjectRegistry:
    all: list = field(default_factory=list)            # tek kaynak: tüm nesneler
    dispatch: dict = field(default_factory=dict)       # (channel, signature_id) -> nesne (sadece RX içerenler)
    periodic_rx: list = field(default_factory=list)    # monitor için
    periodic_tx: list = field(default_factory=list)    # scheduler için

    def clear(self) -> None:
        """Testler arasında temizlik için."""
        self.all.clear()
        self.dispatch.clear()
        self.periodic_rx.clear()
        self.periodic_tx.clear()
