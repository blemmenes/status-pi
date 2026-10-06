"""Bambuddy REST client and background status poller."""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from .config import BambuddyConfig, PrinterConfig
from .state import AppState, PrinterSnapshot

log = logging.getLogger(__name__)


class BambuddyError(Exception):
    pass


def _opt_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _opt_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


class BambuddyClient:
    def __init__(self, cfg: BambuddyConfig) -> None:
        self._cfg = cfg
        self._headers = {"X-API-Key": cfg.api_key, "Accept": "application/json"}

    def _request(self, method: str, path: str, data: bytes | None = None) -> urllib.request.Request:
        return urllib.request.Request(
            f"{self._cfg.base_url}{path}", data=data, headers=self._headers, method=method
        )

    def get_status(self, printer_id: int) -> PrinterSnapshot:
        req = self._request("GET", f"/printers/{printer_id}/status")
        try:
            with urllib.request.urlopen(req, timeout=self._cfg.timeout_seconds) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            raise BambuddyError(f"HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BambuddyError(str(exc)) from exc
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise BambuddyError(f"invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise BambuddyError("invalid JSON: expected an object")
        state = data.get("state")
        return PrinterSnapshot(
            printer_id=printer_id,
            connected=data.get("connected") is True,
            state=state if isinstance(state, str) else None,
            progress=_opt_float(data.get("progress")),
            remaining_minutes=_opt_int(data.get("remaining_time")),
            awaiting_plate_clear=data.get("awaiting_plate_clear") is True,
            fetched_at=time.monotonic(),
        )

    def clear_plate(self, printer_id: int) -> tuple[bool, int | None, str]:
        return self._post(f"/printers/{printer_id}/clear-plate")

    def set_print_speed(self, printer_id: int, mode: int) -> tuple[bool, int | None, str]:
        """mode: 1=silent, 2=standard, 3=sport, 4=ludicrous."""
        return self._post(f"/printers/{printer_id}/print-speed?mode={mode}")

    def _post(self, path: str) -> tuple[bool, int | None, str]:
        req = self._request("POST", path, data=b"")
        try:
            with urllib.request.urlopen(req, timeout=self._cfg.timeout_seconds) as resp:
                status = resp.status
                text = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            status = exc.code
            text = exc.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return False, None, str(exc)
        return status == 200, status, text


def run_poller(
    client: BambuddyClient,
    cfg: BambuddyConfig,
    printers: tuple[PrinterConfig, ...],
    state: AppState,
    stop: threading.Event,
) -> None:
    while not stop.is_set():
        for printer in printers:
            if stop.is_set():
                return
            try:
                snap = client.get_status(printer.id)
            except BambuddyError as exc:
                log.warning("bambuddy poll failed for printer %d: %s", printer.id, exc)
                state.record_poll(False, time.monotonic())
            else:
                state.update_printer(snap)
                state.record_poll(True, time.monotonic())
        state.poll_now.wait(cfg.poll_interval_seconds)
        state.poll_now.clear()
