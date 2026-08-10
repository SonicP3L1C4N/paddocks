"""Talking to a running plasmashell.

Everything here works around two facts that cost a lot of time to discover:

* The desktop scripting engine has no ``Qt`` object, so ``Qt.rect()`` raises
  ReferenceError. Assigning a plain object to ``widget.geometry`` fails
  *silently* -- the read-back still reports the auto-placed position. Widget
  positions can only be set by writing ``ItemGeometries`` into the applet
  config file, and plasmashell overwrites that file on exit, so it has to be
  stopped first.
* ``evaluateScript`` only reliably hands back ``print()`` output. A bare
  trailing expression usually comes back as an empty string.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
APPLETSRC = CONFIG_DIR / "plasma-org.kde.plasma.desktop-appletsrc"


class PlasmaError(RuntimeError):
    pass


def _qdbus() -> str:
    for name in ("qdbus6", "qdbus-qt6", "qdbus"):
        found = shutil.which(name)
        if found:
            return found
    raise PlasmaError("no qdbus binary found (looked for qdbus6, qdbus-qt6, qdbus)")


def _kwriteconfig() -> str:
    for name in ("kwriteconfig6", "kwriteconfig"):
        found = shutil.which(name)
        if found:
            return found
    raise PlasmaError("no kwriteconfig binary found")


def run_script(js: str) -> str:
    """Evaluate JS in plasmashell. Returns whatever the script print()ed."""
    proc = subprocess.run(
        [_qdbus(), "org.kde.plasmashell", "/PlasmaShell",
         "org.kde.PlasmaShell.evaluateScript", js],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise PlasmaError(f"evaluateScript failed: {proc.stderr.strip()}")
    for js_error in ("ReferenceError", "TypeError", "SyntaxError", "RangeError"):
        if js_error in proc.stdout:
            raise PlasmaError(f"script error: {proc.stdout.strip()}")
    return proc.stdout


def is_running() -> bool:
    return subprocess.run(["pgrep", "-x", "plasmashell"],
                          capture_output=True).returncode == 0


def stop() -> None:
    if not is_running():
        return
    quit_cmd = shutil.which("kquitapp6") or shutil.which("kquitapp")
    if not quit_cmd:
        raise PlasmaError("no kquitapp binary found")
    subprocess.run([quit_cmd, "plasmashell"], capture_output=True)
    for _ in range(40):
        if not is_running():
            return
        time.sleep(0.25)
    raise PlasmaError("plasmashell did not exit")


def start() -> None:
    subprocess.Popen(
        ["plasmashell"], start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    for _ in range(60):
        try:
            run_script('print("up")')
            return
        except PlasmaError:
            time.sleep(0.5)
    raise PlasmaError("plasmashell did not come back up")


def screen_geometry(index: int = 0) -> tuple[int, int]:
    out = run_script(
        f'var g = screenGeometry({index});'
        f' print(g.width + "x" + g.height);'
    ).strip()
    w, _, h = out.partition("x")
    return int(w), int(h)


def desktop_containment() -> int:
    """Id of the first desktop containment (the one holding the wallpaper)."""
    out = run_script('print(desktops()[0].id);').strip()
    if not out:
        raise PlasmaError("no desktop containment found")
    return int(out)


def add_folder_widgets(entries: list[tuple[str, str]]) -> dict[str, int]:
    """Create one Folder View widget per (title, url). Returns title -> applet id.

    The url should use the ``desktop:/`` scheme, not ``file://``. Folder View
    renders ``.desktop`` files with their raw filename under ``file://``; only
    the desktop: KIO worker resolves them to application names. That worker
    maps ~/Desktop only, which is why the store has to live there.
    """
    payload = json.dumps([{"title": t, "url": u} for t, u in entries])
    out = run_script(f"""
        var entries = {payload};
        var d = desktops()[0];
        var out = [];
        for (var i = 0; i < entries.length; i++) {{
            var w = d.addWidget("org.kde.plasma.folder");
            w.currentConfigGroup = ["General"];
            w.writeConfig("url", entries[i].url);
            w.writeConfig("labelMode", 3);       // 3 = custom title
            w.writeConfig("labelText", entries[i].title);
            w.reloadConfig();
            out.push(entries[i].title + "\\t" + w.id);
        }}
        print(out.join("\\n"));
    """)
    ids: dict[str, int] = {}
    for line in out.strip().splitlines():
        title, _, wid = line.rpartition("\t")
        if title:
            ids[title] = int(wid)
    if len(ids) != len(entries):
        raise PlasmaError(f"expected {len(entries)} widgets, created {len(ids)}")
    return ids


def remove_widgets(applet_ids: list[int]) -> int:
    payload = json.dumps(applet_ids)
    out = run_script(f"""
        var targets = {payload};
        var d = desktops()[0];
        var removed = 0;
        var ids = d.widgetIds.slice();
        for (var i = 0; i < ids.length; i++) {{
            var w = d.widgetById(ids[i]);
            if (targets.indexOf(w.id) !== -1) {{ w.remove(); removed++; }}
        }}
        print(removed);
    """)
    return int(out.strip() or 0)


def write_item_geometries(containment: int, resolution: str, geometry: str) -> None:
    """Write applet positions. plasmashell MUST be stopped, it rewrites on exit."""
    if is_running():
        raise PlasmaError("refusing to write geometry while plasmashell is running")
    for key in (f"ItemGeometries-{resolution}", "ItemGeometriesHorizontal"):
        subprocess.run(
            [_kwriteconfig(), "--file", APPLETSRC.name,
             "--group", "Containments", "--group", str(containment),
             "--key", key, geometry],
            check=True,
        )


def format_geometries(boxes: list[tuple[int, int, int, int, int]]) -> str:
    """boxes: (applet_id, x, y, w, h) -> 'Applet-1:x,y,w,h,0;...'"""
    return "".join(f"Applet-{i}:{x},{y},{w},{h},0;" for i, x, y, w, h in boxes)


def clear_theme_caches() -> list[Path]:
    """Theme pixmap caches are keyed by theme *name*. Patching a theme in place
    without clearing these serves the old artwork forever."""
    removed = []
    for path in list(CACHE_DIR.glob("plasma_theme_*.kcache")) + [CACHE_DIR / "ksvg-elements"]:
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed
