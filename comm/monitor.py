"""Monitor: periyodik RX mesajlarının zamanında gelip gelmediğini izler.

Kimse mesajı okumasa da geciken/hiç gelmeyen mesajı yakalamak için ayrı çalışır.
Tazelik kuralı her nesnenin RxState'inde (period * tolerance).
"""
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from generic.basemessage import BaseMessageStructure


@dataclass
class StaleReport:
    message: BaseMessageStructure
    age: Optional[float]          # None: hiç gelmedi

    def __str__(self) -> str:
        name = type(self.message).__name__
        if self.age is None:
            return f"{name} @ {self.message.channel}: hiç gelmedi"
        expected = self.message.rx_state.period
        return f"{name} @ {self.message.channel}: {self.age:.3f} sn'dir gelmiyor (periyot {expected} sn)"


class Monitor:
    def __init__(self, *projects: type[BaseMessageStructure],
                 interval: float = 0.1,
                 on_stale: Optional[Callable[[StaleReport], None]] = None):
        self.projects = projects
        self.interval = interval
        self.on_stale = on_stale
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def check(self) -> list[StaleReport]:
        """Bayat olan periyodik RX mesajlarını döndürür."""
        reports = []
        for project in self.projects:
            for reg in project.families():
                for msg in reg.periodic_rx:
                    if not msg.rx_state.is_fresh():
                        reports.append(StaleReport(msg, msg.rx_state.age()))
        return reports

    # ---------------------------------------------------------------- arka plan

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="Monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            for report in self.check():
                if self.on_stale:
                    self.on_stale(report)
