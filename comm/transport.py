"""Transport: sadece byte alır/verir.

Mesajları, signature'ı, periyodu bilmez. Gelen paketi (channel, raw) olarak
kendisine verilen alıcıya (genelde Dispatcher.on_raw) iletir.

Gerçek ortamda (örn. HTTP request ile service'e giden yapı) Transport'tan türeyen bir
sınıf send() içinde request'i atar, gelen veride _deliver() çağırır.
"""
from abc import ABC, abstractmethod
from typing import Callable, Optional

from generic.channel import Channel

Receiver = Callable[[Channel, bytes], object]


class Transport(ABC):
    def __init__(self) -> None:
        self._receiver: Optional[Receiver] = None

    def set_receiver(self, receiver: Receiver) -> None:
        """Gelen paketlerin iletileceği fonksiyon, örn. dispatcher.on_raw."""
        self._receiver = receiver

    @abstractmethod
    def send(self, channel: Channel, data: bytes) -> None:
        """Byte'ları ilgili channel'dan gönderir."""

    def _deliver(self, channel: Channel, data: bytes) -> None:
        """Alt sınıf, bir paket geldiğinde bunu çağırır."""
        if self._receiver is not None:
            self._receiver(channel, data)


class LoopbackTransport(Transport):
    """Örnek/test transport'u.

    Gönderilenleri `sent` listesinde tutar; inject() gelen bir paketi taklit eder.
    """

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[tuple[Channel, bytes]] = []

    def send(self, channel: Channel, data: bytes) -> None:
        self.sent.append((channel, bytes(data)))

    def inject(self, channel: Channel, data: bytes) -> None:
        self._deliver(channel, bytes(data))
