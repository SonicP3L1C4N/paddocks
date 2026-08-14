# SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Shared fixtures.

The hard rule here: no test may touch the real config, the real state file, or
a running plasmashell. `FakePlasma` replaces the whole plasma module rather
than patching its functions one at a time, because patching them individually
means a missed attribute is a test that stops the user's desktop shell — an
accident worth designing out rather than remembering to avoid.
"""

from __future__ import annotations

from pathlib import Path

from paddocks import plasma


def write_desktop(directory: Path, app_id: str, name: str = "", *,
                  categories: str = "", no_display: bool = False,
                  hidden: bool = False, only_show_in: str = "",
                  icon: str = "", entry_type: str = "Application") -> Path:
    """Write a minimal .desktop file for the index to find."""
    directory.mkdir(parents=True, exist_ok=True)
    lines = ["[Desktop Entry]", f"Type={entry_type}",
             f"Name={name or app_id}", "Exec=/bin/true"]
    if categories:
        lines.append(f"Categories={categories}")
    if no_display:
        lines.append("NoDisplay=true")
    if hidden:
        lines.append("Hidden=true")
    if only_show_in:
        lines.append(f"OnlyShowIn={only_show_in}")
    if icon:
        lines.append(f"Icon={icon}")
    path = directory / f"{app_id}.desktop"
    path.write_text("\n".join(lines) + "\n")
    return path


class FakePlasma:
    """A stand-in for the plasma module, recording what it was asked to do."""

    # Re-exported so `except plasma.WidgetCreationError` still matches.
    PlasmaError = plasma.PlasmaError
    WidgetCreationError = plasma.WidgetCreationError

    def __init__(self, state_dir: Path, fail_in: str | None = None,
                 widget_ids: list[int] | None = None):
        self.STATE_DIR = state_dir
        self.calls: list[str] = []
        self._fail_in = fail_in
        self._widget_ids = widget_ids

    def _record(self, name):
        self.calls.append(name)
        if name == self._fail_in:
            raise OSError(f"simulated failure in {name}")

    def screen_geometry(self, index: int = 0):
        self._record("screen_geometry")
        return (1920, 1080)

    def desktop_containment(self):
        self._record("desktop_containment")
        return 1

    def add_quicklaunch_widgets(self, entries):
        self._record("add_quicklaunch_widgets")
        if self._widget_ids is not None:
            return list(self._widget_ids)
        return [100 + i for i in range(len(entries))]

    def add_group_widgets(self, specs):
        self._record("add_group_widgets")
        # Kept so tests can assert which plugin each group asked for.
        self.specs = list(specs)
        if self._widget_ids is not None:
            return list(self._widget_ids)
        return [100 + i for i in range(len(specs))]

    def remove_widgets(self, applet_ids):
        self._record("remove_widgets")
        return len(applet_ids)

    def format_geometries(self, boxes):
        self._record("format_geometries")
        return plasma.format_geometries(boxes)

    def stop(self):
        self._record("stop")

    def start(self):
        self._record("start")

    def backup_appletsrc(self):
        self._record("backup_appletsrc")
        return self.STATE_DIR / "backups" / "fake"

    def write_item_geometries(self, containment, resolution, geometry):
        self._record("write_item_geometries")

    @property
    def shell_calls(self) -> list[str]:
        """Just the stop/start pair, which is what the restart tests assert on."""
        return [c for c in self.calls if c in ("stop", "start")]
