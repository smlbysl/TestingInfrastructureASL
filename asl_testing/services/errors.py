"""ErrorLog: reports communication problems to a separate file (not the messaging history).

Reported: UTS requests that failed (LinkError), periodic RX timeouts and recoveries (from events),
and exceptions raised inside event subscribers (records of the bus logger).
Works from events, so it also works when Comm is given a custom logger.
Its lines do not propagate to the general log, which already has the same problems from the runtime.
(With a custom logger, subscriber exceptions go to that logger, not to this file.)
"""
import logging

from asl_testing.comm import Comm
from asl_testing.events.types import LinkError, RxRestored, RxTimeout

log = logging.getLogger("asl_testing.errors")
log.propagate = False                               # no duplicates in the general log
BUS_LOG = "asl_testing.events.bus"                  # subscriber exceptions


class ErrorLog:
    def __init__(self, comm: Comm, path: str):
        self._handler = logging.FileHandler(path, mode="w", encoding="utf-8")
        self._handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(self._handler)
        log.setLevel(logging.INFO)
        logging.getLogger(BUS_LOG).addHandler(self._handler)
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
        logging.getLogger(BUS_LOG).removeHandler(self._handler)
        self._handler.close()
