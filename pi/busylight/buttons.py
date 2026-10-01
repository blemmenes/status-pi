"""Button A hold -> Bambuddy clear-plate for the printer currently on screen."""

from __future__ import annotations

import logging
import sys
import threading
import time

from .bambuddy import BambuddyClient
from .state import AppState

log = logging.getLogger(__name__)

BUTTON_A = 5
HOLD_SECONDS = 1.0
BOUNCE_SECONDS = 0.05
OK_FEEDBACK_SECONDS = 0.6
ERROR_FEEDBACK_SECONDS = 0.9


class ClearPlateAction:
    def __init__(self, client: BambuddyClient, state: AppState) -> None:
        self._client = client
        self._state = state
        self._busy = threading.Lock()

    def trigger(self) -> None:
        if not self._busy.acquire(blocking=False):
            log.info("clear-plate already in progress")
            return
        try:
            self._trigger()
        finally:
            self._busy.release()

    def _trigger(self) -> None:
        state = self._state
        now = time.monotonic()
        if state.view(now).mic_active:
            log.info("button ignored: mic active")
            return
        pid = state.shown_plate_printer_id
        if pid is None:
            log.info("button ignored: no printer awaiting plate clear")
            return
        try:
            ok, status, body = self._client.clear_plate(pid)
            if ok:
                state.mark_plate_cleared(pid)
                state.set_feedback("ok", now + OK_FEEDBACK_SECONDS)
                log.info("plate cleared for printer %d", pid)
            else:
                state.set_feedback("error", now + ERROR_FEEDBACK_SECONDS)
                log.warning("clear-plate failed for printer %d: %s %s", pid, status, body)
        finally:
            state.poll_now.set()


def start_hardware_buttons(action: ClearPlateAction) -> object:
    """Bind button A (held 1 s). Caller must keep the returned Button referenced."""
    from gpiozero import Button

    button = Button(BUTTON_A, hold_time=HOLD_SECONDS, bounce_time=BOUNCE_SECONDS)
    button.when_held = lambda: action.trigger()
    return button


def start_stdin_buttons(action: ClearPlateAction) -> threading.Thread:
    """Dev stand-in: typing `a` + Enter acts like holding button A."""

    def loop() -> None:
        for line in sys.stdin:
            if line.strip() == "a":
                action.trigger()

    thread = threading.Thread(target=loop, name="stdin-buttons", daemon=True)
    thread.start()
    return thread
