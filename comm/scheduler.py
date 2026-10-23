"""Scheduler: periyodik TX mesajlarını zamanı geldikçe gönderir.

Gönderim: msg.pack() (counter++, checksum, tx_state.on_send) -> transport.send(channel, bytes)
"""
import threading
import time
from typing import Optional

from comm.transport import Transport
from generic.basemessage import BaseMessageStructure


class Scheduler:
    def __init__(self, transport: Transport, *projects: type[BaseMessageStructure],
                 resolution: float = 0.001):
        self.transport = transport
        self.projects = projects
        self.resolution = resolution          # döngü adımı (saniye)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def tick(self, now: Optional[float] = None) -> int:
        """Zamanı gelen mesajları gönderir; gönderilen mesaj sayısını döndürür."""
        now = time.monotonic() if now is None else now
        sent = 0
        for project in self.projects:
            for msg in project.registry().periodic_tx:
                if msg.tx_state.is_due(now):
                    self.transport.send(msg.channel, msg.pack())
                    sent += 1
        return sent

    @staticmethod
    def send(transport: Transport, msg: BaseMessageStructure) -> None:
        """Periyodik olmayan bir mesajı tek seferlik gönderir."""
        transport.send(msg.channel, msg.pack())

    # ---------------------------------------------------------------- arka plan

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="Scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def _run(self) -> None:
        while not self._stop.wait(self.resolution):
            self.tick()
