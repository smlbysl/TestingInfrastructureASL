"""HttpUtsClient: the framework's UtsClient on top of the UTS HTTP API.

Converts links and bytes to UTS JSON and back. If an existing UTS API module is used instead of
UtsApi, only this file changes.

To be confirmed with UTS (see _frame): the layout of one item in the "messages" list
and the unit of its timestamp.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from comm.link import Link
from comm.uts.api import UtsApi
from comm.uts.base import FilterGroups, UtsClient, UtsFetch, UtsFrame
from comm.uts.http import UtsHttp


class HttpUtsClient(UtsClient):
    def __init__(self, base_url: str, timeout: float = 2.0, logger: Optional[logging.Logger] = None):
        self.api = UtsApi(UtsHttp(base_url, timeout, logger))

    def read_config(self, link: Link) -> tuple[dict[str, Any], dict[str, Any]]:
        body = self.api.get_config(link.bus, link.interface).body
        return body.get("configOutput", {}), body.get("deviceStatus", {})

    def write_config(self, link: Link) -> None:
        self.api.post_config(link.bus, link.interface, link.to_uts())

    def transfer(self, link: Link, data: bytes) -> None:
        self.api.post_message(link.bus, link.interface, {"message": list(data)})

    def fetch(self, link: Link) -> UtsFetch:
        body = self.api.get_messages(link.bus, link.interface).body
        frames = [_frame(item) for item in body.get("messages", [])]
        return UtsFetch(frames, bool(body.get("isBufferOverflow", False)))

    def write_filter(self, link: Link, kind: str, groups: FilterGroups) -> None:
        body = {"type": kind,
                "filter": [[{"filterBytePos": pos, "filterValue": value} for pos, value in group]
                           for group in groups]}
        self.api.post_filters(link.bus, link.interface, body)


def _frame(item: Any) -> UtsFrame:
    """One item of the "messages" list -> UtsFrame. Layout to be confirmed with UTS."""
    if isinstance(item, dict):
        return UtsFrame(bytes(item.get("message", [])), item.get("timestamp"))
    return UtsFrame(bytes(item), None)
