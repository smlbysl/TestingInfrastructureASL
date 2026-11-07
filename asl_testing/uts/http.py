"""HttpUtsClient: the real UTS client (placeholder until the UTS API is integrated)."""
from asl_testing.channel.channel import ProtocolType
from asl_testing.uts.client import UtsClient, UtsFrame


class HttpUtsClient(UtsClient):
    """Placeholder for the real UTS client."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    def transfer(self, protocol: ProtocolType, interface: int, data: bytes) -> None:
        raise NotImplementedError("UTS API not integrated yet")

    def fetch(self, protocol: ProtocolType, interface: int) -> list[UtsFrame]:
        raise NotImplementedError("UTS API not integrated yet")
