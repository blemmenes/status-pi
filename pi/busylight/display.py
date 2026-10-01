"""Display backends: Unicorn HAT Mini hardware and an ANSI terminal emulator."""

from __future__ import annotations

import sys

from .scenes import HEIGHT, WIDTH, Frame


class UnicornDisplay:
    def __init__(self, brightness: float, rotation: int) -> None:
        from unicornhatmini import UnicornHATMini

        self._hat = UnicornHATMini()
        self._hat.set_brightness(brightness)
        self._hat.set_rotation(rotation)

    def draw(self, frame: Frame) -> None:
        hat = self._hat
        for y in range(HEIGHT):
            row = frame[y]
            for x in range(WIDTH):
                r, g, b = row[x]
                hat.set_pixel(x, y, r, g, b)
        hat.show()

    def close(self) -> None:
        self._hat.clear()
        self._hat.show()


class TerminalDisplay:
    """Renders frames as 24-bit ANSI background blocks; ignores brightness/rotation."""

    def __init__(self, brightness: float = 1.0, rotation: int = 0) -> None:
        self._out = sys.stdout
        self._out.write("\x1b[2J")
        self._out.flush()

    def draw(self, frame: Frame) -> None:
        lines = [
            "".join(f"\x1b[48;2;{r};{g};{b}m  \x1b[0m" for r, g, b in row) for row in frame
        ]
        self._out.write("\x1b[H" + "\n".join(lines) + "\n")
        self._out.flush()

    def close(self) -> None:
        self._out.write("\x1b[0m\n")
        self._out.flush()
