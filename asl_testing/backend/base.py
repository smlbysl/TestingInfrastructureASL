"""Backend: the system between the test PC and the device. The core gives and takes bytes on the line.

    send(channel, data)     sends the bytes on the channel's interface -> Response
    receive(channel)        Response whose data is the list of Received since the last call

A backend does not raise for a failed request: it returns a Response with ok False.
How the bytes reach the device (HTTP, JSON, paths) is known only inside the backend.
"""

__author__ = "İsmail Baysal"

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Received:
    data: bytes                         # bytes on the line
    timestamp: Optional[float]          # backend time in seconds


@dataclass(frozen=True)
class Response:
    """Result of one request. True in a condition when the request succeeded."""
    ok: bool
    status: Optional[int] = None        # status code of the backend (HTTP code); None: not reached
    code: Optional[str] = None          # error code of the backend
    message: Optional[str] = None       # error text
    data: Any = None                    # body of a successful request
    timestamp: Optional[float] = None   # backend time of the request in seconds, if reported
    elapsed: float = 0.0                # duration of the request in seconds

    def __bool__(self) -> bool:
        return self.ok


class BackendError(Exception):
    """A backend request failed; response holds the details."""

    def __init__(self, response: Response):
        super().__init__(f"status {response.status}, code {response.code}: {response.message}")
        self.response = response


class Backend(ABC):
    control = None                      # configuration and filters, if the backend has them

    @abstractmethod
    def send(self, channel, data: bytes) -> Response:
        """Sends the bytes on the line of a channel."""

    @abstractmethod
    def receive(self, channel) -> Response:
        """What the channel's interface received since the last call; data is a list of Received."""
