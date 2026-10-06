from busylight.config import PrinterConfig
from busylight.font import DIGITS
from busylight.scenes import (
    AMBER,
    BLACK,
    GREEN,
    IDLE_OK,
    PROGRESS_ROW,
    RED,
    WIDTH,
    compose,
)
from busylight.state import PrinterSnapshot, StateView

P1 = PrinterConfig(id=11, index=1, color=(0, 160, 255))
P2 = PrinterConfig(id=22, index=2, color=(180, 0, 255))
TWO = (P1, P2)
ONE = (P1,)


def snap(pid, *, state="RUNNING", progress=10.0, remaining=30, awaiting=False, fetched_at=0.0, connected=True):
    return PrinterSnapshot(
        printer_id=pid,
        connected=connected,
        state=state,
        progress=progress,
        remaining_minutes=remaining,
        awaiting_plate_clear=awaiting,
        fetched_at=fetched_at,
    )


def view(*snaps, mic=False, terminal=None, ok=True, feedback=None):
    return StateView(
        mic_active=mic,
        printers={s.printer_id: s for s in snaps},
        last_terminal_state=terminal or {},
        bambuddy_ok=ok,
        feedback=feedback,
    )


def glyph_at(frame, x0, color):
    """Return the glyph drawn in `color` at (x0, 0), or None if the cell is empty."""
    rows = tuple(
        "".join("1" if frame[y][x0 + dx] == color else "0" for dx in range(3)) for y in range(5)
    )
    if rows == ("000",) * 5:
        return None
    for ch, glyph in DIGITS.items():
        if glyph == rows:
            return ch
    raise AssertionError(f"unrecognised glyph at x={x0}: {rows}")


def read_time(frame, color):
    return [glyph_at(frame, x, color) for x in (0, 4, 10, 14)]


def all_pixels(frame):
    return {px for row in frame for px in row}


def test_mic_beats_awaiting_beats_printing():
    printing = snap(P1.id)
    awaiting = snap(P2.id, state="FINISH", awaiting=True)
    assert compose(view(printing, awaiting, mic=True), TWO, 0.0).screen == "mic"
    res = compose(view(printing, awaiting, mic=True), TWO, 0.0)
    assert all_pixels(res.frame) == {RED}
    assert compose(view(printing, awaiting), TWO, 0.0).screen == "plate_clear"
    assert compose(view(printing), TWO, 0.0).screen == "eta"


def test_countdown_shows_hours_and_minutes_remaining():
    res = compose(view(snap(P1.id, remaining=95)), ONE, 0.0)
    assert res.screen == "eta"
    assert read_time(res.frame, P1.color) == [None, "1", "3", "5"]
    assert res.frame[1][8] == P1.color and res.frame[3][8] == P1.color


def test_countdown_under_an_hour_shows_zero_hours():
    res = compose(view(snap(P1.id, remaining=7)), ONE, 0.0)
    assert read_time(res.frame, P1.color) == [None, "0", "0", "7"]


def test_countdown_two_digit_hours():
    res = compose(view(snap(P1.id, remaining=12 * 60 + 5)), ONE, 0.0)
    assert read_time(res.frame, P1.color) == ["1", "2", "0", "5"]


def test_countdown_clamps_at_99_59():
    res = compose(view(snap(P1.id, remaining=100 * 60)), ONE, 0.0)
    assert read_time(res.frame, P1.color) == ["9", "9", "5", "9"]


def test_eta_unknown_remaining_shows_dashes_without_colon():
    res = compose(view(snap(P1.id, remaining=None)), ONE, 0.0)
    assert read_time(res.frame, P1.color) == ["-", "-", "-", "-"]
    assert res.frame[1][8] == BLACK


def test_two_printers_cycle_with_index_dot():
    v = view(snap(P1.id), snap(P2.id))
    first = compose(v, TWO, 0.0)
    second = compose(v, TWO, 5.0)
    assert first.frame[5][0] == P1.color and first.frame[5][2] == BLACK
    assert second.frame[5][2] == P2.color and second.frame[5][0] == BLACK
    assert read_time(second.frame, P2.color)[1] is not None


def test_single_printer_has_no_index_dot():
    res = compose(view(snap(P1.id)), ONE, 0.0)
    assert res.frame[5][0] == BLACK


def test_progress_bar_half():
    res = compose(view(snap(P1.id, progress=50)), ONE, 0.0)
    lit = [x for x in range(WIDTH) if res.frame[PROGRESS_ROW][x] != BLACK]
    assert lit == list(range(8))


def test_paused_digits_blink():
    v = view(snap(P1.id, state="PAUSE"))
    assert read_time(compose(v, ONE, 0.0).frame, P1.color)[1] is not None
    assert read_time(compose(v, ONE, 0.6).frame, P1.color) == [None] * 4


def _dominant(frame):
    # Pulse peaks at now = PULSE_PERIOD / 2; pick a lit pixel not covered by the cut-out digit.
    return frame[0][0]


def test_awaiting_failed_is_amber():
    res = compose(view(snap(P1.id, state="FAILED", awaiting=True)), ONE, 1.0)
    assert res.screen == "plate_clear"
    assert _dominant(res.frame) == AMBER


def test_awaiting_idle_without_history_is_green():
    res = compose(view(snap(P1.id, state="IDLE", awaiting=True)), ONE, 1.0)
    assert _dominant(res.frame) == GREEN


def test_awaiting_idle_after_failure_is_amber():
    v = view(snap(P1.id, state="IDLE", awaiting=True), terminal={P1.id: "FAILED"})
    assert _dominant(compose(v, ONE, 1.0).frame) == AMBER


def test_plate_clear_cuts_out_printer_number_when_multiple():
    v = view(snap(P1.id, state="FINISH", awaiting=True), snap(P2.id, state="FINISH", awaiting=True))
    res = compose(v, TWO, 6.0)  # second cycle slot -> printer 2
    assert res.shown_plate_printer_id == P2.id
    for dy, row in enumerate(DIGITS["2"]):
        for dx, bit in enumerate(row):
            lit = res.frame[1 + dy][7 + dx] != BLACK
            assert lit == (bit == "0")


def test_stale_snapshot_is_ignored():
    res = compose(view(snap(P1.id, awaiting=True, fetched_at=0.0)), ONE, 121.0)
    assert res.screen == "idle"
    assert res.frame[6][16] == IDLE_OK


def test_shown_plate_printer_only_on_plate_clear():
    printing = snap(P1.id)
    awaiting = snap(P2.id, state="FINISH", awaiting=True)
    assert compose(view(printing, awaiting), TWO, 0.0).shown_plate_printer_id == P2.id
    assert compose(view(printing, awaiting, mic=True), TWO, 0.0).shown_plate_printer_id is None
    assert compose(view(printing), TWO, 0.0).shown_plate_printer_id is None
    assert compose(view(), TWO, 0.0).shown_plate_printer_id is None


def test_shown_print_printer_follows_countdown_on_screen():
    printing = (snap(P1.id), snap(P2.id))
    assert compose(view(*printing), TWO, 0.0).shown_print_printer_id == P1.id
    assert compose(view(*printing), TWO, 6.0).shown_print_printer_id == P2.id
    awaiting = snap(P2.id, state="FINISH", awaiting=True)
    assert compose(view(snap(P1.id), awaiting), TWO, 0.0).shown_print_printer_id is None
    assert compose(view(*printing, mic=True), TWO, 0.0).shown_print_printer_id is None
    assert compose(view(), TWO, 0.0).shown_print_printer_id is None
