"""Dispatcher: gelen ham paketi ilgili mesaj nesnesine yazar.

Akış: Transport -> Dispatcher.on_raw(channel, raw) -> ProjectX.lookup(channel, raw) -> obj.decode(raw)
- Hiçbir projede eşleşmeyen paket `unknown`a,
- eşleşip validate'ten (boy / length / checksum) geçemeyen paket `invalid`e düşer.
"""
from collections import deque
from typing import Callable, Optional

from generic.basemessage import BaseMessageStructure
from generic.channel import Channel


class Dispatcher:
    def __init__(self, *projects: type[BaseMessageStructure],
                 on_unknown: Optional[Callable[[Channel, bytes], None]] = None,
                 on_invalid: Optional[Callable[[BaseMessageStructure, bytes], None]] = None,
                 history: int = 100):
        self.projects = projects                       # örn. (ProjectBase1, ProjectBase2)
        self.on_unknown = on_unknown
        self.on_invalid = on_invalid
        self.unknown: deque = deque(maxlen=history)    # (channel, raw)
        self.invalid: deque = deque(maxlen=history)    # (nesne, raw)

    def on_raw(self, channel: Channel, raw: bytes) -> Optional[BaseMessageStructure]:
        for project in self.projects:
            msg = project.lookup(channel, raw)
            if msg is None:
                continue
            if msg.decode(raw):
                return msg
            self.invalid.append((msg, raw))
            if self.on_invalid:
                self.on_invalid(msg, raw)
            return None

        self.unknown.append((channel, raw))
        if self.on_unknown:
            self.on_unknown(channel, raw)
        return None
