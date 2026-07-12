from __future__ import annotations

"""Stdlib HTTP bridge for the web UI.

Serves the single-page app from ``static/`` and forwards ``/api/...``
requests to :class:`~topik_sim.web.app.WebApp`. Threading keeps slow TTS
synthesis requests from blocking navigation. Binds to localhost only —
this is a private, single-user tool.
"""

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .app import WebApp

STATIC_DIR = Path(__file__).parent / "static"
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".wav": "audio/wav",
}


def _make_handler(app: WebApp):
    class Handler(BaseHTTPRequestHandler):
        server_version = "topik-sim-web"

        def log_message(self, format: str, *args) -> None:  # quiet by default
            pass

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def _dispatch(self, method: str) -> None:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._api(method, parsed)
            elif method == "GET":
                self._static(parsed.path)
            else:
                self._send_json(405, {"error": "Method not allowed."})

        def _api(self, method: str, parsed) -> None:
            query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            body = {}
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                try:
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._send_json(400, {"error": "Body must be JSON."})
                    return
            status, payload = app.handle(method, parsed.path, query, body)
            if isinstance(payload, tuple):  # (bytes, content_type) — audio
                data, content_type = payload
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            self._send_json(status, payload)

        def _static(self, path: str) -> None:
            name = path.lstrip("/") or "index.html"
            target = (STATIC_DIR / name).resolve()
            if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
                # Unknown paths fall back to the app shell (client-side views).
                target = STATIC_DIR / "index.html"
                if not target.is_file():
                    self._send_json(404, {"error": "Not found."})
                    return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPES.get(target.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, status: int, payload) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def run_server(app: WebApp, host: str = "127.0.0.1", port: int = 8765,
               open_browser: bool = True) -> int:
    server = ThreadingHTTPServer((host, port), _make_handler(app))
    url = f"http://{host}:{port}/"
    print(f"TOPIK simulator web UI: {url}  (Ctrl+C stops the server)")
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0
