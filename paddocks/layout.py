"""Working out where each group goes.

The numbers below are not guesses -- they were derived by asking Plasma for a
size and reading back what it actually applied. Folder View refuses to go
below roughly 400x304, so small groups end up larger than their contents need.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Metrics:
    cell: int = 140          # icon + label cell
    header: int = 44         # title bar of the group
    pad_x: int = 32          # frame margins, left + right
    pad_y: int = 28          # frame margin below the last icon row
    min_width: int = 180
    min_height: int = 150
    max_columns: int = 4     # cap so wide groups wrap instead of stretching
    margin: int = 60         # screen edge inset
    gap: int = 24            # space between groups
    top: int = 48            # y of the first row
    reserve_bottom: int = 80 # panel allowance


@dataclass
class Box:
    name: str
    x: int
    y: int
    w: int
    h: int
    rows: int = 1   # Quicklaunch maxSectionCount: how many icon rows to wrap into


def size_for(count: int, m: Metrics) -> tuple[int, int, int]:
    """Size a group to hold `count` icons. Returns (width, height, rows).

    Quicklaunch flows icons into a single row unless maxSectionCount caps the
    row count, so the solver has to hand that number to the widget as well.
    """
    columns = max(1, min(m.max_columns, count))
    rows = max(1, math.ceil(count / columns))
    w = columns * m.cell + m.pad_x
    h = m.header + rows * m.cell + m.pad_y
    return max(w, m.min_width), max(h, m.min_height), rows


def solve(groups: list[tuple[str, int]], screen: tuple[int, int],
          m: Metrics, arrangement: str = "row") -> list[Box]:
    """groups: [(name, item_count)]. Returns placed boxes."""
    if arrangement == "row":
        return _flow(groups, screen, m, columns=None)
    if arrangement == "grid":
        return _flow(groups, screen, m, columns=3)
    if arrangement == "column":
        return _flow(groups, screen, m, columns=1)
    raise ValueError(f"unknown arrangement {arrangement!r}")


def _flow(groups, screen, m: Metrics, columns: int | None) -> list[Box]:
    """Lay groups out left to right, wrapping when the row is full.

    `columns` forces a wrap after N groups; None wraps only on running out of
    horizontal room, which gives the single-row-across-the-top arrangement on
    a wide screen and degrades sanely on a narrow one.
    """
    screen_w, screen_h = screen
    limit = screen_w - m.margin
    boxes: list[Box] = []

    x, y, row_h, in_row = m.margin, m.top, 0, 0
    for name, count in groups:
        w, h, rows = size_for(count, m)
        wrap = (columns is not None and in_row >= columns) or \
               (columns is None and in_row > 0 and x + w > limit)
        if wrap:
            x = m.margin
            y += row_h + m.gap
            row_h, in_row = 0, 0
        boxes.append(Box(name, x, y, w, h, rows))
        x += w + m.gap
        row_h = max(row_h, h)
        in_row += 1

    overflow = (y + row_h) - (screen_h - m.reserve_bottom)
    if overflow > 0:
        raise ValueError(
            f"layout is {overflow}px taller than the usable screen; "
            f"reduce max_columns, cell size, or use fewer groups"
        )
    return boxes
