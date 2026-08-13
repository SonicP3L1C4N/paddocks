"""Putting Paddocks in the application menu.

Deliberately free of any Qt import: installing the menu entry is a file copy,
and there is no reason to need PyQt6 to do it.

The .desktop file is generated rather than shipped, because ``Exec=`` has to
carry the absolute path of wherever this was cloned to. A checked-in file would
be wrong for everyone but its author.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

ICON_SOURCE = Path(__file__).resolve().parent.parent / "icons"
ENTRY_POINT = Path(__file__).resolve().parent.parent / "bin" / "paddocks"

DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
APPLICATIONS = DATA_HOME / "applications"
HICOLOR = DATA_HOME / "icons/hicolor"

ICON_NAME = "paddocks"
DESKTOP_FILE = f"{ICON_NAME}.desktop"
SIZES = (32, 64, 128, 256, 512)
VARIANTS = ("dark", "light")

ENTRY = """\
[Desktop Entry]
Type=Application
Version=1.0
Name=Paddocks
GenericName=Desktop Groups
Comment=Group desktop launchers into titled panels
Exec={exec_line}
Icon={icon}
Terminal=false
Categories=Utility;Qt;KDE;
Keywords=desktop;groups;launcher;panel;icons;
StartupWMClass={icon}
"""


def preferred_variant() -> str:
    """Pick the icon that suits the current colour scheme.

    Read out of kdeglobals rather than asked of Qt, so that the command line
    can install the right one without PyQt6 present.
    """
    kdeglobals = Path(os.environ.get("XDG_CONFIG_HOME",
                                     Path.home() / ".config")) / "kdeglobals"
    try:
        text = kdeglobals.read_text()
    except OSError:
        return "dark"

    match = re.search(r"^\[Colors:Window\]\s*$.*?^BackgroundNormal=(\d+),(\d+),(\d+)",
                      text, re.M | re.S)
    if not match:
        return "dark"
    red, green, blue = (int(part) for part in match.groups())
    # Rec. 601 luma: a mid-grey desktop should read as dark, and a plain
    # average makes green count for far too little.
    luma = 0.299 * red + 0.587 * green + 0.114 * blue
    return "dark" if luma < 128 else "light"


def install(variant: str | None = None) -> list[Path]:
    variant = variant or preferred_variant()
    if variant not in VARIANTS:
        raise ValueError(f"unknown icon variant {variant!r}; use dark or light")
    if not ENTRY_POINT.exists():
        raise FileNotFoundError(f"cannot find the paddocks entry point at {ENTRY_POINT}")

    written: list[Path] = []
    for size in SIZES:
        source = ICON_SOURCE / f"{ICON_NAME}-{variant}-{size}.png"
        if not source.exists():
            continue
        target = HICOLOR / f"{size}x{size}" / "apps" / f"{ICON_NAME}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written.append(target)

    source = ICON_SOURCE / f"{ICON_NAME}-{variant}.svg"
    if source.exists():
        target = HICOLOR / "scalable" / "apps" / f"{ICON_NAME}.svg"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written.append(target)

    if not written:
        raise FileNotFoundError(f"no {variant} icons found in {ICON_SOURCE}")

    APPLICATIONS.mkdir(parents=True, exist_ok=True)
    entry = APPLICATIONS / DESKTOP_FILE
    entry.write_text(ENTRY.format(exec_line=_exec_line(), icon=ICON_NAME))
    entry.chmod(0o755)
    written.append(entry)

    _refresh_caches()
    return written


def uninstall() -> list[Path]:
    removed: list[Path] = []
    for size in SIZES:
        target = HICOLOR / f"{size}x{size}" / "apps" / f"{ICON_NAME}.png"
        if target.exists():
            target.unlink()
            removed.append(target)
    for target in (HICOLOR / "scalable" / "apps" / f"{ICON_NAME}.svg",
                   APPLICATIONS / DESKTOP_FILE):
        if target.exists():
            target.unlink()
            removed.append(target)
    _refresh_caches()
    return removed


def installed_entry() -> Path | None:
    entry = APPLICATIONS / DESKTOP_FILE
    return entry if entry.exists() else None


def _exec_line() -> str:
    """`Exec=` with the absolute path, quoted if the clone lives somewhere
    with a space in the name."""
    path = str(ENTRY_POINT)
    if any(character in path for character in ' \t"\'\\'):
        path = '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f"{path} edit"


def _refresh_caches() -> None:
    """Best effort: the menu picks the entry up on its own soon enough."""
    for command in (["update-desktop-database", str(APPLICATIONS)],
                    ["gtk-update-icon-cache", "-qtf", str(HICOLOR)]):
        binary = shutil.which(command[0])
        if binary:
            subprocess.run([binary, *command[1:]], capture_output=True)
