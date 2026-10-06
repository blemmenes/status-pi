"""Thread-safe shared application state."""

from __future__ import annotations

import dataclasses
import threading
from dataclasses import dataclass
from typing import Literal

FeedbackKind = Literal["ok", "error"]
TERMINAL_STATES = ("FINISH", "FAILED")


@dataclass(frozen=True)
class PrinterSnapshot:
    printer_id: int
    connected: bool
    state: str | None
    progress: float | None
    remaining_minutes: int | None
    awaiting_plate_clear: bool
    fetched_at: float  # time.monotonic()


@dataclass(frozen=True)
class Feedback:
    kind: FeedbackKind
    until: float


@dataclass(frozen=True)
class StateView:
    mic_active: bool
    printers: dict[int, PrinterSnapshot]
    last_terminal_state: dict[int, str]
    bambuddy_ok: bool
    feedback: Feedback | None


class AppState:
    def __init__(self, poll_interval_seconds: float) -> None:
        self._lock = threading.Lock()
        self._poll_interval = poll_interval_seconds
        self._mic_until = 0.0
        self._printers: dict[int, PrinterSnapshot] = {}
        self._last_terminal_state: dict[int, str] = {}
        self._last_poll_ok_at: float | None = None
        self._feedback: Feedback | None = None
        self._shown_plate_printer_id: int | None = None
        self._shown_print_printer_id: int | None = None
        self._last_screen = "idle"
        self.poll_now = threading.Event()

    # Mic
    def set_mic(self, active: bool, ttl: float, now: float) -> None:
        with self._lock:
            self._mic_until = now + ttl if active else 0.0

    def mic_active(self, now: float) -> bool:
        with self._lock:
            return now < self._mic_until

    # Printers
    def update_printer(self, snap: PrinterSnapshot) -> None:
        with self._lock:
            self._printers[snap.printer_id] = snap
            if snap.state in TERMINAL_STATES:
                self._last_terminal_state[snap.printer_id] = snap.state

    def mark_plate_cleared(self, printer_id: int) -> None:
        with self._lock:
            snap = self._printers.get(printer_id)
            if snap is not None:
                self._printers[printer_id] = dataclasses.replace(snap, awaiting_plate_clear=False)

    # Poll health
    def record_poll(self, ok: bool, now: float) -> None:
        with self._lock:
            if ok:
                self._last_poll_ok_at = now

    # Button feedback
    def set_feedback(self, kind: FeedbackKind, until: float) -> None:
        with self._lock:
            self._feedback = Feedback(kind, until)

    # Render-loop outputs
    @property
    def shown_plate_printer_id(self) -> int | None:
        with self._lock:
            return self._shown_plate_printer_id

    @shown_plate_printer_id.setter
    def shown_plate_printer_id(self, value: int | None) -> None:
        with self._lock:
            self._shown_plate_printer_id = value

    @property
    def shown_print_printer_id(self) -> int | None:
        with self._lock:
            return self._shown_print_printer_id

    @shown_print_printer_id.setter
    def shown_print_printer_id(self, value: int | None) -> None:
        with self._lock:
            self._shown_print_printer_id = value

    @property
    def last_screen(self) -> str:
        with self._lock:
            return self._last_screen

    @last_screen.setter
    def last_screen(self, value: str) -> None:
        with self._lock:
            self._last_screen = value

    def view(self, now: float) -> StateView:
        with self._lock:
            ok_at = self._last_poll_ok_at
            return StateView(
                mic_active=now < self._mic_until,
                printers=dict(self._printers),
                last_terminal_state=dict(self._last_terminal_state),
                bambuddy_ok=ok_at is not None and now - ok_at <= 3 * self._poll_interval,
                feedback=self._feedback,
            )
