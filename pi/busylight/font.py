"""3x5 pixel digit font."""

from __future__ import annotations

Color = tuple[int, int, int]

# Rows top to bottom; "1" = lit.
DIGITS: dict[str, tuple[str, ...]] = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "001", "001", "001"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "-": ("000", "000", "111", "000", "000"),
}


def draw_glyph(frame: list[list[Color]], ch: str, x0: int, y0: int, color: Color) -> None:
    """Set the lit pixels of glyph `ch` with its top-left at (x0, y0)."""
    for dy, row in enumerate(DIGITS[ch]):
        for dx, bit in enumerate(row):
            if bit == "1":
                frame[y0 + dy][x0 + dx] = color
