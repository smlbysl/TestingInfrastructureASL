"""Channel: mesajın hangi protokol + interface üzerinden gidip geldiği.

Service tarafında interface'ler (ip/port vb.) tanımlı; request'te protokol de iletiliyor.
İkisinin birleşimi bir channel'dır. Hash'lenebilir olduğu için dispatch anahtarında kullanılır.
"""
from dataclasses import dataclass

from generic.enumerations import ProtocolType


@dataclass(frozen=True)
class Channel:
    protocol: ProtocolType
    interface: int

    def __str__(self) -> str:
        return f"{self.protocol.name}:{self.interface}"
