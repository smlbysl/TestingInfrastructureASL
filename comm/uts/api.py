"""UtsApi: one method per UTS endpoint, JSON in and out. bus is "ethernet" or "serials"."""
from comm.uts.http import UtsHttp, UtsResponse


class UtsApi:
    def __init__(self, http: UtsHttp):
        self.http = http

    def get_bus_configs(self, bus: str) -> UtsResponse:
        """All interfaces of a bus (e.g. interfaceList / moxaList)."""
        return self.http.request("GET", f"/{bus}/configs")

    def get_config(self, bus: str, interface: int) -> UtsResponse:
        return self.http.request("GET", f"/{bus}/{interface}/configs")

    def post_config(self, bus: str, interface: int, body: dict) -> UtsResponse:
        return self.http.request("POST", f"/{bus}/{interface}/configs", body)

    def get_messages(self, bus: str, interface: int) -> UtsResponse:
        return self.http.request("GET", f"/{bus}/{interface}/messages")

    def post_message(self, bus: str, interface: int, body: dict) -> UtsResponse:
        return self.http.request("POST", f"/{bus}/{interface}/messages", body)

    def get_filters(self, bus: str, interface: int) -> UtsResponse:
        return self.http.request("GET", f"/{bus}/{interface}/filters")

    def post_filters(self, bus: str, interface: int, body: dict) -> UtsResponse:
        return self.http.request("POST", f"/{bus}/{interface}/filters", body)
