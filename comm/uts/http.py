"""UtsHttp: sends one HTTP request to UTS and returns status code, headers and body.

Every UTS answer carries statusInfo {status, code, message}; a status other than "OK"
or an HTTP error raises UtsError.
"""
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from comm.uts.base import UtsError


@dataclass(frozen=True)
class UtsResponse:
    status_code: int
    headers: dict[str, str]
    body: dict[str, Any]


class UtsHttp:
    def __init__(self, base_url: str, timeout: float = 2.0, logger: Optional[logging.Logger] = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.log = logger or logging.getLogger(__name__)

    def request(self, method: str, path: str, body: Optional[dict] = None) -> UtsResponse:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        self.log.debug("%s %s %s", method, path, body if body is not None else "")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                status, head, text = r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            status, head, text = e.code, dict(e.headers), e.read()
        except (urllib.error.URLError, OSError) as e:
            self.log.error("%s %s: UTS unreachable: %s", method, path, e)
            raise UtsError(f"{method} {path}: UTS unreachable: {e}") from e

        payload = json.loads(text) if text else {}
        info = payload.get("statusInfo", {})
        if status >= 400 or info.get("status", "OK") != "OK":
            message = info.get("message", "")
            self.log.error("%s %s failed: HTTP %s %s", method, path, status, message)
            raise UtsError(f"{method} {path} failed: HTTP {status} {message}")
        self.log.debug("%s %s -> %s %s", method, path, status, info.get("message", ""))
        return UtsResponse(status, head, payload)
