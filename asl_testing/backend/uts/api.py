"""UtsApi: the requests to UTS (UTS is an HTTP service; every body is JSON).

    POST /{path}/{interface}/messages     sends one message
        200  {"statusInfo": {"status": "OK", "code": 200, "message": "..."}, "timestamp": 1731500000000000}
        400  empty message / port closed     404  invalid interface
        500  HAL timeout                     503  eINIT mode
    GET  /{path}/{interface}/messages     what was received since the last call; empties the buffer of UTS
        200  {"statusInfo": {...}, "messages": [{"message": [1, 2, 3], "timestamp": 1731500000000000}],
              "isBufferOverflow": false}
        404  invalid interface               503  eINIT mode

An error has the same statusInfo (status, code, message). uts_response() turns the HTTP code and the
JSON body into a Response; the fields of a successful body are read by the codec of the bus.

path is the root of the bus in the UTS URL ("serials", "ethernet", "1553"). The body of a POST and
the items of a GET are built and read by the codec of the bus (codecs.py); this class passes them
as they are and returns every result as a Response. A failed request does not raise.
timeout is the time to wait for the answer in seconds; UtsBackend gives it with every request.
Duration, logging and the one-POST-per-interface rule are handled by UtsBackend, not here.

WrapperUtsApi is the place to connect the existing ApiWrapper; its methods are to be filled in.
"""

__author__ = "İsmail Baysal"

from abc import ABC, abstractmethod
from typing import Optional

from asl_testing.backend.base import Response

FilterGroups = list[list[tuple[int, int]]]   # OR of groups; a group is an AND of (byte position, value)


def uts_response(status: Optional[int], body: Optional[dict]) -> Response:
    """Response of a UTS answer: HTTP code and JSON body (None if there was no body)."""
    info = (body or {}).get("statusInfo") or {}
    ok = status == 200
    return Response(ok=ok, status=status, code=info.get("status"), message=info.get("message"),
                    data=body if ok else None)


class UtsApi(ABC):
    @abstractmethod
    def post(self, path: str, interface: int, body: dict, timeout: float) -> Response:
        """Sends one message; body comes from the codec."""

    @abstractmethod
    def get(self, path: str, interface: int, timeout: float) -> Response:
        """What was received since the last call; Response.data is the JSON body."""

    # ---------------------------------------------------------------- management (optional)

    def get_config(self, path: str, interface: int) -> dict:
        """Settings of an interface."""
        raise NotImplementedError

    def set_config(self, path: str, interface: int, settings: dict) -> None:
        """Writes settings of an interface."""
        raise NotImplementedError

    def get_filter(self, path: str, interface: int) -> tuple[str, FilterGroups]:
        """Receive filter as (kind, groups); kind "NONE" means no filter."""
        raise NotImplementedError

    def set_filter(self, path: str, interface: int, kind: str, groups: FilterGroups) -> None:
        """kind "INCLUSIVE": only the groups pass; "NONE": no filter."""
        raise NotImplementedError


class WrapperUtsApi(UtsApi):
    """UTS through the ApiWrapper of the script object.

        comm = Comm(UtsBackend(WrapperUtsApi(script.api)), [ProjectBase])

    To fill in: call the wrapper and turn its answer into a Response.
        the wrapper gives the HTTP code and the JSON body     return uts_response(code, body)
        the wrapper gives something else, build it by hand:
            success   Response(ok=True, status=200, data=body)       body as in the module text above
            error     Response(ok=False, status=..., code=..., message=...)
        no answer     Response(ok=False, message="timeout")          (status stays None)
    """

    def __init__(self, wrapper):
        self.wrapper = wrapper

    def post(self, path: str, interface: int, body: dict, timeout: float) -> Response:
        raise NotImplementedError("WrapperUtsApi.post: call the ApiWrapper here")

    def get(self, path: str, interface: int, timeout: float) -> Response:
        raise NotImplementedError("WrapperUtsApi.get: call the ApiWrapper here")
