"""Pure scene composition: StateView -> 17x7 frame."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import PrinterConfig
from .font import Color, draw_glyph
from .state import PrinterSnapshot, StateView

WIDTH = 17
HEIGHT = 7

Frame = list[list[Color]]

BLACK: Color = (0, 0, 0)
RED: Color = (255, 0, 0)
GREEN: Color = (0, 255, 0)
AMBER: Color = (255, 140, 0)
PURPLE: Color = (160, 0, 255)
WHITE: Color = (200, 200, 200)
IDLE_OK: Color = (40, 40, 40)
IDLE_ERR: Color = (60, 0, 60)

CYCLE_SECONDS = 5.0
PULSE_PERIOD = 2.0
STALE_SECONDS = 120.0
ACTIVE_STATES = frozenset({"RUNNING", "PAUSE", "PREPARE", "SLICING"})

FLASH_INTERVAL = 0.15
PAUSE_BLINK_INTERVAL = 0.5
PROGRESS_SCALE = 0.4

# Countdown layout
MAX_COUNTDOWN_MINUTES = 99 * 60 + 59  # four digits: 99:59
DIGIT_X = (0, 4, 10, 14)  # hour tens, hour ones, minute tens, minute ones
COLON = ((8, 1), (8, 3))
INDEX_ROW = 5
PROGRESS_ROW = 6
IDLE_PIXEL = (16, 6)
PLATE_DIGIT_ORIGIN = (7, 1)


@dataclass(frozen=True)
class ComposeResult:
    frame: Frame
    screen: str  # "mic" | "feedback" | "plate_clear" | "eta" | "idle"
    shown_plate_printer_id: int | None
    shown_print_printer_id: int | None = None  # printer whose countdown is on screen ("eta")


def blank_frame() -> Frame:
    return [[BLACK] * WIDTH for _ in range(HEIGHT)]


def filled_frame(color: Color) -> Frame:
    return [[color] * WIDTH for _ in range(HEIGHT)]


def _scale(color: Color, k: float) -> Color:
    return (round(color[0] * k), round(color[1] * k), round(color[2] * k))


def _cycle_pick(items: list[tuple[PrinterConfig, PrinterSnapshot]], now: float):
    return items[int(now // CYCLE_SECONDS) % len(items)]


def compose(view: StateView, printers: tuple[PrinterConfig, ...], now: float) -> ComposeResult:
    if view.mic_active:
        return ComposeResult(filled_frame(RED), "mic", None)

    fb = view.feedback
    if fb is not None and now < fb.until:
        color = WHITE if fb.kind == "ok" else PURPLE
        on = int(now / FLASH_INTERVAL) % 2 == 0
        return ComposeResult(filled_frame(color) if on else blank_frame(), "feedback", None)

    fresh: list[tuple[PrinterConfig, PrinterSnapshot]] = []
    for printer in printers:
        snap = view.printers.get(printer.id)
        if snap is not None and now - snap.fetched_at <= STALE_SECONDS:
            fresh.append((printer, snap))
    multi = len(printers) > 1

    awaiting = [(p, s) for p, s in fresh if s.awaiting_plate_clear]
    if awaiting:
        printer, sel = _cycle_pick(awaiting, now)
        if sel.state == "FINISH":
            base = GREEN
        elif sel.state == "FAILED":
            base = AMBER
        else:
            base = AMBER if view.last_terminal_state.get(sel.printer_id) == "FAILED" else GREEN
        k = 0.15 + 0.85 * (0.5 - 0.5 * math.cos(2 * math.pi * now / PULSE_PERIOD))
        frame = filled_frame(_scale(base, k))
        if multi:
            draw_glyph(frame, str(printer.index), *PLATE_DIGIT_ORIGIN, BLACK)
        return ComposeResult(frame, "plate_clear", sel.printer_id)

    printing = [(p, s) for p, s in fresh if s.connected and s.state in ACTIVE_STATES]
    if printing:
        printer, sel = _cycle_pick(printing, now)
        col = printer.color
        frame = blank_frame()
        show_digits = sel.state != "PAUSE" or int(now / PAUSE_BLINK_INTERVAL) % 2 == 0
        remaining = sel.remaining_minutes
        if remaining is None or remaining <= 0:
            if show_digits:
                for x in DIGIT_X:
                    draw_glyph(frame, "-", x, 0, col)
        else:
            hours, minutes = divmod(min(remaining, MAX_COUNTDOWN_MINUTES), 60)
            if show_digits:
                if hours >= 10:
                    draw_glyph(frame, str(hours // 10), DIGIT_X[0], 0, col)
                draw_glyph(frame, str(hours % 10), DIGIT_X[1], 0, col)
                for x, y in COLON:
                    frame[y][x] = col
                draw_glyph(frame, str(minutes // 10), DIGIT_X[2], 0, col)
                draw_glyph(frame, str(minutes % 10), DIGIT_X[3], 0, col)
        if multi:
            frame[INDEX_ROW][2 * (printer.index - 1)] = col
        n = max(0, min(WIDTH, int((sel.progress or 0) * WIDTH // 100)))
        dim = _scale(col, PROGRESS_SCALE)
        for x in range(n):
            frame[PROGRESS_ROW][x] = dim
        return ComposeResult(frame, "eta", None, sel.printer_id)

    frame = blank_frame()
    frame[IDLE_PIXEL[1]][IDLE_PIXEL[0]] = IDLE_OK if view.bambuddy_ok else IDLE_ERR
    return ComposeResult(frame, "idle", None)
