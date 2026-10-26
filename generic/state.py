"""Yöne göre mesaj nesnesine eklenen durum parçaları.

RX içeren mesajda rx_state, TX içeren mesajda tx_state bulunur; çift yönlü mesajda ikisi de.
Ayar (Timing) sabittir; burada sadece değişen değerler tutulur.
"""
import time
from dataclasses import dataclass
from typing import Optional

from generic.timing import Timing


@dataclass
class RxState:
    timing: Timing
    last_time: Optional[float] = None    # son geçerli paketin zamanı (time.monotonic)
    count: int = 0                       # geçerli paket sayısı
    errors: int = 0                      # validate'ten geçemeyen paket sayısı

    def on_receive(self) -> None:
        self.last_time = time.monotonic()
        self.count += 1

    def on_error(self) -> None:
        self.errors += 1

    def age(self) -> Optional[float]:
        """Son paketten bu yana geçen süre; hiç gelmediyse None."""
        if self.last_time is None:
            return None
        return time.monotonic() - self.last_time

    def is_fresh(self) -> bool:
        if self.last_time is None:
            return False                 # hiç gelmedi
        if not self.timing.is_periodic:
            return True                  # event mesajı
        return self.age() <= self.timing.period * self.timing.tolerance


@dataclass
class TxState:
    timing: Timing
    last_time: Optional[float] = None    # son gönderim zamanı (time.monotonic)
    count: int = 0

    def on_send(self) -> None:
        self.last_time = time.monotonic()
        self.count += 1

    def is_due(self, now: Optional[float] = None) -> bool:
        """Periyodik mesajın gönderim zamanı geldi mi?"""
        if not self.timing.is_periodic:
            return False
        if self.last_time is None:
            return True
        now = time.monotonic() if now is None else now
        return now - self.last_time >= self.timing.period
