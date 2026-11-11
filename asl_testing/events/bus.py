"""EventBus: publish / subscribe between the layers.

publish() returns at once. Each subscriber has its own queue and thread, so a slow subscriber
does not hold up the publisher or the others. A subscription is by event type (`object` = all),
optionally for one message object (where=). An exception in a handler is logged.
"""

__author__ = "İsmail Baysal"
import logging
import queue
import threading
from collections import defaultdict
from typing import Any, Callable, Optional

Handler = Callable[[Any], None]
_STOP = object()


class Subscriber(threading.Thread):
    def __init__(self, event_type: type, handler: Handler, where: Optional[object], name: str, log):
        super().__init__(name=name, daemon=True)
        self.log = log
        self.event_type = event_type
        self.handler = handler
        self.where = where                    # message object, or None for all
        self.queue: queue.Queue = queue.Queue()

    def accepts(self, event) -> bool:
        return self.where is None or getattr(event, "message", None) is self.where

    def run(self) -> None:
        while True:
            event = self.queue.get()
            if event is _STOP:
                break
            try:
                self.handler(event)
            except Exception:
                self.log.exception("subscriber %s failed on %s", self.name, type(event).__name__)

    def stop(self) -> None:
        self.queue.put(_STOP)


class EventBus:
    def __init__(self, log=None):
        self.log = log or logging.getLogger(__name__)
        self._subs: dict[type, list[Subscriber]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event_type: type, handler: Handler,
                  where: Optional[object] = None, name: Optional[str] = None) -> Subscriber:
        sub = Subscriber(event_type, handler, where, name or getattr(handler, "__name__", "subscriber"), self.log)
        with self._lock:
            self._subs[event_type].append(sub)
        sub.start()
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        """Stops a subscription; a second call does nothing."""
        with self._lock:
            subs = self._subs[sub.event_type]
            if sub not in subs:
                return
            subs.remove(sub)
        sub.stop()

    def publish(self, event) -> None:
        with self._lock:
            subs = list(self._subs[type(event)]) + list(self._subs[object])
        for sub in subs:
            if sub.accepts(event):
                sub.queue.put(event)

    def close(self) -> None:
        """Stops all subscribers after their queued events."""
        with self._lock:
            subs = [s for group in self._subs.values() for s in group]
            self._subs.clear()
        for sub in subs:
            sub.stop()
        for sub in subs:
            sub.join()
