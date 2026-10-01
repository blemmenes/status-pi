from busylight.state import AppState, PrinterSnapshot


def test_mic_ttl_expires():
    state = AppState(poll_interval_seconds=10)
    state.set_mic(True, 90, now=1000.0)
    assert state.view(1089.0).mic_active
    assert not state.view(1091.0).mic_active


def test_mic_false_clears_immediately():
    state = AppState(poll_interval_seconds=10)
    state.set_mic(True, 90, now=1000.0)
    state.set_mic(False, 90, now=1001.0)
    assert not state.view(1001.0).mic_active


def test_terminal_state_survives_later_idle_and_plate_clear_is_optimistic():
    state = AppState(poll_interval_seconds=10)
    base = dict(printer_id=1, connected=True, progress=100.0, remaining_minutes=0, fetched_at=0.0)
    state.update_printer(PrinterSnapshot(state="FAILED", awaiting_plate_clear=True, **base))
    state.update_printer(PrinterSnapshot(state="IDLE", awaiting_plate_clear=True, **base))
    state.mark_plate_cleared(1)
    v = state.view(0.0)
    assert v.last_terminal_state == {1: "FAILED"}
    assert v.printers[1].awaiting_plate_clear is False


def test_bambuddy_ok_window():
    state = AppState(poll_interval_seconds=10)
    assert not state.view(0.0).bambuddy_ok
    state.record_poll(True, 100.0)
    state.record_poll(False, 110.0)
    assert state.view(130.0).bambuddy_ok
    assert not state.view(131.0).bambuddy_ok
