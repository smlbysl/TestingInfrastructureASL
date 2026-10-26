"""Timing: mesajın zamanlama ayarı (sabit).

- period None ise mesaj olay tabanlıdır (event), değilse periyodiktir.
- frozen olduğu için proje varsayılanı olarak tüm nesneler arasında paylaşılabilir.
- Değişen değerler (son geliş/gönderim zamanı, sayaçlar) RxState / TxState'te tutulur.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Timing:
    period: Optional[float] = None       # saniye; None -> event
    tolerance: float = 2.0               # RX: period * tolerance aşılırsa veri bayat

    @property
    def is_periodic(self) -> bool:
        return self.period is not None
