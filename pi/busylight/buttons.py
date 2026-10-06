"""Unicorn HAT Mini buttons -> Bambuddy actions for the printer currently on screen.

A (top left, held 1 s):     clear-plate for the printer awaiting plate clear.
X (top right, held 1 s):    print speed -> sport for the printer whose countdown is shown.
Y (bottom right, held 1 s): print speed -> standard for the printer whose countdown is shown.
"""

from __future__ import annotations

import logging
import sys
import threading
import time

from .bambuddy import BambuddyClient
from .state import AppState

log = logging.getLogger(__name__)

BUTTON_PINS = {"a": 5, "x": 16, "y": 24}  # BCM pins
HOLD_SECONDS = 1.0
BOUNCE_SECONDS = 0.05
OK_FEEDBACK_SECONDS = 0.6
ERROR_FEEDBACK_SECONDS = 0.9

SPEED_STANDARD = 2
SPEED_SPORT = 3


class _Action:
    """Runs one Bambuddy call at a time, ignored while the mic screen is up."""

    name = ""

    def __init__(self, client: BambuddyClient, state: AppState) -> None:
        self._client = client
        self._state = state
        self._busy = threading.Lock()

    def trigger(self) -> None:
        if not self._busy.acquire(blocking=False):
            log.info("%s already in progress", self.name)
            return
        try:
            now = time.monotonic()
            if self._state.view(now).mic_active:
                log.info("%s ignored: mic active", self.name)
                return
            self._run(now)
        finally:
            self._busy.release()

    def _run(self, now: float) -> None:
        raise NotImplementedError

    def _finish(self, ok: bool, now: float) -> None:
        if ok:
            self._state.set_feedback("ok", now + OK_FEEDBACK_SECONDS)
        else:
            self._state.set_feedback("error", now + ERROR_FEEDBACK_SECONDS)
        self._state.poll_now.set()


class ClearPlateAction(_Action):
    name = "clear-plate"

    def _run(self, now: float) -> None:
        pid = self._state.shown_plate_printer_id
        if pid is None:
            log.info("clear-plate ignored: no printer awaiting plate clear")
            return
        ok = False
        try:
            ok, status, body = self._client.clear_plate(pid)
            if ok:
                self._state.mark_plate_cleared(pid)
                log.info("plate cleared for printer %d", pid)
            else:
                log.warning("clear-plate failed for printer %d: %s %s", pid, status, body)
        finally:
            self._finish(ok, now)


class PrintSpeedAction(_Action):
    def __init__(self, client: BambuddyClient, state: AppState, mode: int, label: str) -> None:
        super().__init__(client, state)
        self._mode = mode
        self.name = f"speed-{label}"

    def _run(self, now: float) -> None:
        pid = self._state.shown_print_printer_id
        if pid is None:
            log.info("%s ignored: no print on screen", self.name)
            return
        ok = False
        try:
            ok, status, body = self._client.set_print_speed(pid, self._mode)
            if ok:
                log.info("%s set for printer %d", self.name, pid)
            else:
                log.warning("%s failed for printer %d: %s %s", self.name, pid, status, body)
        finally:
            self._finish(ok, now)


def make_actions(client: BambuddyClient, state: AppState) -> dict[str, _Action]:
    """Actions keyed by button name (keys of BUTTON_PINS)."""
    return {
        "a": ClearPlateAction(client, state),
        "x": PrintSpeedAction(client, state, SPEED_SPORT, "sport"),
        "y": PrintSpeedAction(client, state, SPEED_STANDARD, "standard"),
    }


def start_hardware_buttons(actions: dict[str, _Action]) -> list[object]:
    """Bind each button (held 1 s). Caller must keep the returned Buttons referenced."""
    from gpiozero import Button

    buttons = []
    for key, action in actions.items():
        button = Button(BUTTON_PINS[key], hold_time=HOLD_SECONDS, bounce_time=BOUNCE_SECONDS)
        button.when_held = action.trigger
        buttons.append(button)
    return buttons


def start_stdin_buttons(actions: dict[str, _Action]) -> threading.Thread:
    """Dev stand-in: typing a button name (`a`, `x`, `y`) + Enter acts like holding it."""

    def loop() -> None:
        for line in sys.stdin:
            action = actions.get(line.strip())
            if action is not None:
                action.trigger()

    thread = threading.Thread(target=loop, name="stdin-buttons", daemon=True)
    thread.start()
    return thread
