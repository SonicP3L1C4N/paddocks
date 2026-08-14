# SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Working out where each group goes.

The numbers below are not guesses -- they were derived by asking Plasma for a
size and reading back what it actually applied. Folder View refuses to go
below roughly 400x304, so small groups end up larger than their contents need.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

ARRANGEMENTS = ("row", "grid", "column")
ALIGNMENTS = ("center", "left")

# Folder View will not render below roughly this, whatever geometry it is given
# -- it clamps internally and the box ends up mismatched with what was written.
# Measured by writing progressively smaller ItemGeometries and reading back what
# survived a plasmashell restart.
FOLDER_MIN_WIDTH = 400
FOLDER_MIN_HEIGHT = 304

# A folder's contents change under you, so there is no count to size from. This
# is the nominal capacity a folder group is sized for, overridable per group.
FOLDER_CELLS = 8


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
    align: str = "center"    # "center" or "left" within each row


@dataclass
class Box:
    name: str
    x: int
    y: int
    w: int
    h: int
    rows: int = 1   # Quicklaunch maxSectionCount: how many icon rows to wrap into


def size_for(count: int, m: Metrics, folder: bool = False) -> tuple[int, int, int]:
    """Size a group to hold `count` icons. Returns (width, height, rows).

    Quicklaunch flows icons into a single row unless maxSectionCount caps the
    row count, so the solver has to hand that number to the widget as well.

    `folder` sizes a Folder View instead: same grid arithmetic so folder groups
    share the visual rhythm of app groups, but floored at the size Folder View
    refuses to go below. `count` is then a nominal capacity rather than a real
    item count -- the folder decides for itself what it holds, and scrolls when
    it holds more.
    """
    columns = max(1, min(m.max_columns, count))
    rows = max(1, math.ceil(count / columns))
    # Quicklaunch balances icons across the rows it is given: 6 in 2 rows
    # renders 3+3, not 4+2. Size the box to the balanced column count, or it
    # comes out too wide, Quicklaunch scales the icons up to fill it, and every
    # group ends up a different icon size.
    columns = math.ceil(count / rows)
    w = columns * m.cell + m.pad_x
    h = m.header + rows * m.cell + m.pad_y
    if folder:
        return max(w, FOLDER_MIN_WIDTH), max(h, FOLDER_MIN_HEIGHT), rows
    return max(w, m.min_width), max(h, m.min_height), rows


def solve(groups: list[tuple], screen: tuple[int, int],
          m: Metrics, arrangement: str = "row") -> list[Box]:
    """groups: [(name, item_count)] or [(name, item_count, is_folder)].

    The two-item form is the app-group case and stays the whole story for
    callers that have no folders.
    """
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
    rows_of_boxes: list[list[Box]] = []

    x, y, row_h, in_row = m.margin, m.top, 0, 0
    for entry in groups:
        name, count = entry[0], entry[1]
        folder = entry[2] if len(entry) > 2 else False
        w, h, rows = size_for(count, m, folder=folder)
        wrap = (columns is not None and in_row >= columns) or \
               (columns is None and in_row > 0 and x + w > limit)
        if wrap:
            x = m.margin
            y += row_h + m.gap
            row_h, in_row = 0, 0
        box = Box(name, x, y, w, h, rows)
        boxes.append(box)
        if in_row == 0:
            rows_of_boxes.append([])
        rows_of_boxes[-1].append(box)
        x += w + m.gap
        row_h = max(row_h, h)
        in_row += 1

    if m.align == "center":
        _center(rows_of_boxes, screen_w)

    overflow = (y + row_h) - (screen_h - m.reserve_bottom)
    if overflow > 0:
        raise ValueError(
            f"layout is {overflow}px taller than the usable screen; "
            f"reduce max_columns, cell size, or use fewer groups"
        )
    return boxes


def _center(rows_of_boxes: list[list[Box]], screen_w: int) -> None:
    """Centre each row horizontally, and centre shorter groups within it.

    Groups in a row differ in height whenever they differ in icon-row count,
    so left/top alignment leaves a ragged bottom edge. Centring both axes makes
    a mixed row read as one deliberate band.
    """
    for row in rows_of_boxes:
        if not row:
            continue
        span = (row[-1].x + row[-1].w) - row[0].x
        shift = (screen_w - span) // 2 - row[0].x
        tallest = max(b.h for b in row)
        for box in row:
            box.x += shift
            box.y += (tallest - box.h) // 2
