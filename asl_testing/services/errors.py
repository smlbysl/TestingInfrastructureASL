"""ErrorLog: writes communication problems to a separate file.

Written: failed UTS requests (LinkError), RX timeouts and recoveries, exceptions in subscribers.
Built on events, so it also works with a custom Comm logger (subscriber exceptions then go to that
logger). Its records do not go to the general log, which has the same problems already.
"""

__author__ = "İsmail Baysal"

import logging

from asl_testing.comm import Comm
from asl_testing.events.types import LinkError, RxRestored, RxTimeout

log = logging.getLogger("asl_testing.errors")
log.propagate = False
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
