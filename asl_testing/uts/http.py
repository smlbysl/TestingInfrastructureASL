"""HttpUtsClient: the real UTS client (placeholder until the UTS API is known)."""

__author__ = "İsmail Baysal"

from asl_testing.uts.client import UtsClient


class HttpUtsClient(UtsClient):
    def __init__(self, base_url: str):
        self.base_url = base_url

    def post(self, path: str, interface: int, body: dict) -> None:
        raise NotImplementedError("UTS API not integrated yet")

    def get(self, path: str, interface: int) -> list[dict]:
        raise NotImplementedError("UTS API not integrated yet")
