"""Small authenticated HTTP API: mic state in, status out."""

from __future__ import annotations

import hmac
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .config import Config
from .state import AppState

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 1024


def start_http_server(cfg: Config, state: AppState) -> ThreadingHTTPServer:
    expected_auth = f"Bearer {cfg.http.token}".encode()

    class Handler(BaseHTTPRequestHandler):
        server_version = "busylight"

        def log_message(self, format: str, *args: Any) -> None:
            log.debug("%s " + format, self.address_string(), *args)

        def _send(self, status: int, body: bytes = b"", content_type: str | None = None) -> None:
            self.send_response(status)
            if content_type:
                self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _json(self, status: int, payload: Any) -> None:
            self._send(status, json.dumps(payload).encode(), "application/json")

        def _authorized(self) -> bool:
            got = self.headers.get("Authorization", "").encode()
            if hmac.compare_digest(got, expected_auth):
                return True
            self._json(401, {"error": "unauthorized"})
            return False

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._send(200, b"ok", "text/plain")
            elif self.path == "/api/state":
                if self._authorized():
                    self._json(200, _state_payload(cfg, state))
            elif self.path.startswith("/api/"):
                if self._authorized():
                    self._json(404, {"error": "not found"})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if not self.path.startswith("/api/"):
                self._json(404, {"error": "not found"})
                return
            if not self._authorized():
                return
            if self.path != "/api/mic":
                self._json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length > MAX_BODY_BYTES:
                self.close_connection = True
                self._json(413, {"error": "body too large"})
                return
            body = self.rfile.read(length) if length > 0 else b""
            try:
                data = json.loads(body)
            except ValueError:
                data = None
            if not isinstance(data, dict) or not isinstance(data.get("active"), bool):
                self._json(400, {"error": 'expected {"active": bool}'})
                return
            active = data["active"]
            now = time.monotonic()
            before = state.mic_active(now)
            state.set_mic(active, cfg.mic.ttl_seconds, now)
            if state.mic_active(now) != before:
                log.info("mic active=%s", active)
            self._send(204)

    server = ThreadingHTTPServer((cfg.http.bind, cfg.http.port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="http", daemon=True).start()
    return server


def _state_payload(cfg: Config, state: AppState) -> dict[str, Any]:
    now = time.monotonic()
    view = state.view(now)
    printers = []
    for printer in cfg.printers:
        snap = view.printers.get(printer.id)
        printers.append(
            {
                "id": printer.id,
                "connected": snap.connected if snap else None,
                "state": snap.state if snap else None,
                "progress": snap.progress if snap else None,
                "remaining_minutes": snap.remaining_minutes if snap else None,
                "awaiting_plate_clear": snap.awaiting_plate_clear if snap else None,
                "age_seconds": round(now - snap.fetched_at, 1) if snap else None,
            }
        )
    return {
        "mic_active": view.mic_active,
        "bambuddy_ok": view.bambuddy_ok,
        "screen": state.last_screen,
        "shown_plate_printer_id": state.shown_plate_printer_id,
        "shown_print_printer_id": state.shown_print_printer_id,
        "printers": printers,
    }
