"""python -m busylight --config PATH [--fake-display] [--log-level INFO]"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time

from .bambuddy import BambuddyClient, run_poller
from .buttons import make_actions, start_hardware_buttons, start_stdin_buttons
from .config import ConfigError, load_config
from .http_api import start_http_server
from .scenes import compose
from .state import AppState

FRAME_INTERVAL = 0.1  # 10 Hz

log = logging.getLogger("busylight")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="busylight")
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--fake-display", action="store_true", help="render to the terminal; type a/x/y + Enter for buttons A/X/Y"
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        # Keep stdout free for the terminal display.
        stream=sys.stderr,
    )

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    state = AppState(cfg.bambuddy.poll_interval_seconds)
    client = BambuddyClient(cfg.bambuddy)
    stop = threading.Event()

    threading.Thread(
        target=run_poller,
        args=(client, cfg.bambuddy, cfg.printers, state, stop),
        name="poller",
        daemon=True,
    ).start()
    server = start_http_server(cfg, state)
    log.info("listening on %s:%d", *server.server_address[:2])

    if args.fake_display:
        from .display import TerminalDisplay

        display = TerminalDisplay(cfg.brightness, cfg.rotation)
    else:
        from .display import UnicornDisplay

        display = UnicornDisplay(cfg.brightness, cfg.rotation)

    actions = make_actions(client, state)
    # Held so gpiozero's Buttons are not garbage collected.
    button_source = start_stdin_buttons(actions) if args.fake_display else start_hardware_buttons(actions)

    def on_signal(signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    last_frame = None
    try:
        while not stop.is_set():
            now = time.monotonic()
            res = compose(state.view(now), cfg.printers, now)
            state.shown_plate_printer_id = res.shown_plate_printer_id
            state.shown_print_printer_id = res.shown_print_printer_id
            state.last_screen = res.screen
            if res.frame != last_frame:
                display.draw(res.frame)
                last_frame = res.frame
            stop.wait(FRAME_INTERVAL)
    finally:
        state.poll_now.set()
        server.shutdown()
        server.server_close()
        display.close()
        del button_source
    log.info("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
