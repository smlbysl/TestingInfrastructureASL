"""ErrorLog: reports communication problems to a separate file (not the messaging history).

Reported: UTS requests that failed (LinkError), periodic RX timeouts and recoveries,
and exceptions raised inside event subscribers (logged by the bus on the "comm" logger).
"""
import logging

from comm.comm import Comm
from events.types import LinkError, RxRestored, RxTimeout

log = logging.getLogger("comm")


class ErrorLog:
    def __init__(self, comm: Comm, path: str):
        self._handler = logging.FileHandler(path, mode="w", encoding="utf-8")
        self._handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(self._handler)
        log.setLevel(logging.INFO)
        self._sub = comm.subscribe(object, self._on_event)

    def _on_event(self, event) -> None:
        if isinstance(event, LinkError):
            log.error("UTS %s failed on %s: %r", event.operation, event.channel, event.error)
        elif isinstance(event, RxTimeout):
            log.warning("%s on %s not received for %.3f s (period %s s)", type(event.message).__name__,
                        event.message._channel, event.age, event.message._rx.timing.period)
        elif isinstance(event, RxRestored):
            log.info("%s on %s received again", type(event.message).__name__, event.message._channel)

    def close(self) -> None:
        """Call after comm.close()."""
        log.removeHandler(self._handler)
        self._handler.close()
