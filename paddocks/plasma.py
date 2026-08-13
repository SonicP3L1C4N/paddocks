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
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "paddocks"
APPLETSRC = CONFIG_DIR / "plasma-org.kde.plasma.desktop-appletsrc"

BACKUP_DIR = STATE_DIR / "backups"
KEEP_BACKUPS = 5

PLASMA_UNIT = "plasma-plasmashell.service"


class PlasmaError(RuntimeError):
    pass


class WidgetCreationError(PlasmaError):
    """Widget creation failed partway. `ids` are the applets that do exist.

    Carrying them out lets the caller record them, so a half-built desktop can
    still be cleaned up with `paddocks remove` instead of by hand.
    """

    def __init__(self, message: str, ids: list[int]):
        super().__init__(message)
        self.ids = ids


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


def run_script(js: str, check: bool = True) -> str:
    """Evaluate JS in plasmashell. Returns whatever the script print()ed.

    `check=False` is for scripts that catch their own errors and print partial
    results alongside them; the caller then decides what to raise.
    """
    proc = subprocess.run(
        [_qdbus(), "org.kde.plasmashell", "/PlasmaShell",
         "org.kde.PlasmaShell.evaluateScript", js],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise PlasmaError(f"evaluateScript failed: {proc.stderr.strip()}")
    if check:
        for js_error in ("ReferenceError", "TypeError", "SyntaxError", "RangeError"):
            if js_error in proc.stdout:
                raise PlasmaError(f"script error: {proc.stdout.strip()}")
    return proc.stdout


def is_running() -> bool:
    return subprocess.run(["pgrep", "-x", "plasmashell"],
                          capture_output=True).returncode == 0


def stop() -> None:
    """Quit plasmashell, wherever it happens to live.

    kquitapp rather than ``systemctl stop`` because the running shell is not
    necessarily in ``plasma-plasmashell.service`` -- an earlier version of
    Paddocks orphaned it into the launching app's transient unit, and this
    quits it either way. The unit's ``Restart=on-failure`` does not fire on a
    clean exit, so `start` is left to put it back.
    """
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


def unit_is_known() -> bool:
    """Whether this session has a systemd unit for plasmashell.

    ``systemctl --user cat`` exits non-zero when there is no such unit, which
    covers both a session without a systemd user manager and a Plasma started
    by some other means.
    """
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return False
    return subprocess.run(
        [systemctl, "--user", "cat", PLASMA_UNIT],
        capture_output=True,
    ).returncode == 0


def start() -> None:
    """Bring plasmashell back up.

    Asking systemd rather than spawning the binary is not a tidiness
    preference. A child process inherits our cgroup -- ``start_new_session``
    changes the session id, not the unit -- so a plasmashell spawned from here
    lands in whatever transient ``app-*.service`` the desktop made to launch
    *Paddocks*. Those units are ``KillMode=control-group``, so the shell then
    dies with the terminal or menu entry that started us, and meanwhile
    ``plasma-plasmashell.service`` sits inactive and no longer describes the
    running desktop.
    """
    if unit_is_known():
        systemctl = shutil.which("systemctl")
        # The unit is Type=dbus, so systemd returns once plasmashell has taken
        # org.kde.plasmashell and there is nothing left for us to poll for.
        proc = subprocess.run(
            [systemctl, "--user", "start", PLASMA_UNIT],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            return
        # Fall through rather than raise: a masked or otherwise broken unit
        # should leave the user with a desktop, not without one.

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


def add_quicklaunch_widgets(entries: list[tuple[str, list[str], int]]) -> list[int]:
    """Create one Quicklaunch widget per (title, launcher urls, rows).

    Returns the applet ids in the order given -- by position, not by title, so
    that two groups sharing a name cannot quietly lose one of them.

    Quicklaunch stores ``file://`` URLs pointing straight at the installed
    ``.desktop`` files and renders them by application name. Folder View was
    the obvious choice here and is the wrong one: pointed at a plain
    ``file://`` folder it labels every entry with its raw filename, and pointed
    at ``desktop:/`` it labels them correctly but will not launch anything and
    never notices files being added. See the README.
    """
    payload = json.dumps([{"title": t, "urls": u, "rows": r} for t, u, r in entries])
    # The script catches its own errors so that the ids created before the
    # failure still come back and can be recorded by the caller.
    out = run_script(f"""
        var entries = {payload};
        var d = desktops()[0];
        var out = [];
        var err = "";
        try {{
            for (var i = 0; i < entries.length; i++) {{
                var w = d.addWidget("org.kde.plasma.quicklaunch");
                w.currentConfigGroup = ["General"];
                w.writeConfig("launcherUrls", entries[i].urls);
                w.writeConfig("title", entries[i].title);
                w.writeConfig("showLauncherNames", true);
                w.writeConfig("enablePopup", false);
                // Without this Quicklaunch flows everything into one row and
                // shrinks the icons to fit, so icon size varies per group.
                w.writeConfig("maxSectionCount", entries[i].rows);
                w.reloadConfig();
                out.push(w.id);
            }}
        }} catch (e) {{
            err = String(e);
        }}
        print("IDS " + out.join(","));
        if (err) print("ERR " + err);
    """, check=False)

    ids: list[int] = []
    error = ""
    for line in out.splitlines():
        if line.startswith("IDS "):
            ids = [int(i) for i in line[4:].split(",") if i.strip()]
        elif line.startswith("ERR "):
            error = line[4:].strip()

    if error:
        raise WidgetCreationError(f"creating widgets failed: {error}", ids)
    if len(ids) != len(entries):
        raise WidgetCreationError(
            f"expected {len(entries)} widgets, created {len(ids)}", ids)
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


def backup_appletsrc() -> Path | None:
    """Copy the desktop layout aside before we rewrite part of it.

    ``ItemGeometries`` is private API in a file that also holds every panel,
    widget and wallpaper setting the user has. Restoring is a plain copy back
    with plasmashell stopped, which is worth the few kilobytes a run costs.
    """
    if not APPLETSRC.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Timestamped so the names sort in age order and mean something to whoever
    # is reading the directory to pick one to restore.
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"{APPLETSRC.name}.{stamp}"
    for attempt in range(2, 100):
        if not target.exists():
            break
        target = BACKUP_DIR / f"{APPLETSRC.name}.{stamp}-{attempt}"
    shutil.copy2(APPLETSRC, target)

    existing = sorted(BACKUP_DIR.glob(f"{APPLETSRC.name}.*"))
    for stale in existing[:-KEEP_BACKUPS]:
        stale.unlink(missing_ok=True)
    return target


def write_item_geometries(containment: int, resolution: str, geometry: str) -> None:
    """Write applet positions. plasmashell MUST be stopped, it rewrites on exit."""
    if is_running():
        raise PlasmaError("refusing to write geometry while plasmashell is running")
    for key in (f"ItemGeometries-{resolution}", "ItemGeometriesHorizontal"):
        proc = subprocess.run(
            [_kwriteconfig(), "--file", APPLETSRC.name,
             "--group", "Containments", "--group", str(containment),
             "--key", key, geometry],
            capture_output=True, text=True,
        )
        # Raised as PlasmaError rather than left as CalledProcessError, which
        # is a SubprocessError and so escapes the CLI's handler as a traceback.
        if proc.returncode != 0:
            raise PlasmaError(
                f"kwriteconfig failed writing {key} "
                f"(exit {proc.returncode}): {proc.stderr.strip()}"
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
