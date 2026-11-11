"""MonitorService: local web page to watch message values over time, live or from a CSV.

    monitor = MonitorService(comm, [ProjectBase], port=8050)   # comm=None: CSV import only
    monitor.start()                                            # http://localhost:8050
    monitor.stop()

Page: File > Import CSV / Clear, Tools > Start / Stop, message tree on the left, one chart per
signal on the right. Standard library only; the page needs no internet.

API (JSON):
    GET  /api/state                      source, listening, t0, message streams
    GET  /api/fields?id=<stream>         fields of a stream with their latest values
    POST /api/series                     {"signals": [{"id", "path", "from"}]} -> new points
    POST /api/start | /api/stop | /api/clear
    POST /api/import?name=<file>         body: CommLogger CSV text
"""

__author__ = "İsmail Baysal"

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Sequence
from urllib.parse import parse_qs, urlparse

from asl_testing.events.types import MessageReceived, MessageSent
from asl_testing.services.monitor.recorder import Recorder

PAGE = Path(__file__).with_name("page.html")
log = logging.getLogger(__name__)


class MonitorService:
    def __init__(self, comm=None, projects: Sequence[type] = (), port: int = 8050, host: str = "127.0.0.1"):
        self.comm = comm
        self.recorder = Recorder(projects)
        self.host, self.port = host, port
        self._subs: list = []
        self._server: Optional[ThreadingHTTPServer] = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    # ---------------------------------------------------------------- web server

    def start(self) -> None:
        """Starts the web server; recording starts with listen() or Tools > Start."""
        self._server = ThreadingHTTPServer((self.host, self.port), _handler(self))
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, name="MonitorWeb", daemon=True).start()
        log.info("monitor on %s", self.url)

    def stop(self) -> None:
        self.unlisten()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    # ---------------------------------------------------------------- recording

    @property
    def listening(self) -> bool:
        return bool(self._subs)

    def listen(self) -> None:
        """Starts recording the messages of comm."""
        if self.comm is None:
            raise RuntimeError("no Comm given: offline mode (import a CSV)")
        if self._subs:
            return
        if not self.recorder.source.startswith("live"):
            self.recorder.clear()                       # live data replaces an imported CSV
        self.recorder.source = "live"
        self._subs = [self.comm.subscribe(MessageReceived, self.recorder.on_event),
                      self.comm.subscribe(MessageSent, self.recorder.on_event)]

    def unlisten(self) -> None:
        for sub in self._subs:
            self.comm.bus.unsubscribe(sub)
        self._subs = []

    # ---------------------------------------------------------------- API

    def state(self) -> dict:
        return {"source": self.recorder.source, "listening": self.listening, "live": self.comm is not None,
                "t0": self.recorder.t0(), "messages": self.recorder.message_list()}

    def series(self, request: dict) -> dict:
        out = []
        for sig in request.get("signals", []):
            try:
                times, values, nxt = self.recorder.series(sig["id"], sig["path"], int(sig.get("from", 0)))
            except KeyError:
                times, values, nxt = [], [], 0
            out.append({"id": sig["id"], "path": sig["path"], "t": times, "v": values, "next": nxt})
        return {"t0": self.recorder.t0(), "series": out}


def _handler(service: MonitorService):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, body, code: int = 200) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> bytes:
            return self.rfile.read(int(self.headers.get("Content-Length", 0)))

        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/":
                data = PAGE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif url.path == "/api/state":
                self._json(service.state())
            elif url.path == "/api/fields":
                try:
                    self._json(service.recorder.fields(query["id"][0]))
                except KeyError:
                    self._json({"error": "unknown stream"}, 404)
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            url = urlparse(self.path)
            try:
                if url.path == "/api/series":
                    self._json(service.series(json.loads(self._body() or b"{}")))
                elif url.path == "/api/start":
                    service.listen()
                    self._json(service.state())
                elif url.path == "/api/stop":
                    service.unlisten()
                    self._json(service.state())
                elif url.path == "/api/clear":
                    service.recorder.clear()
                    self._json(service.state())
                elif url.path == "/api/import":
                    name = parse_qs(url.query).get("name", [""])[0]
                    service.unlisten()
                    service.recorder.clear()
                    count = service.recorder.load_csv(self._body().decode("utf-8"), name)
                    self._json({"loaded": count, **service.state()})
                else:
                    self._json({"error": "not found"}, 404)
            except Exception as error:                       # shown in the page's status bar
                log.exception("monitor request %s failed", url.path)
                self._json({"error": str(error)}, 400)

    return Handler
