"""Building the groups themselves."""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import plasma
from .layout import Metrics, solve

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "paddocks"
STATE_FILE = STATE_DIR / "state.json"

# Where .desktop files are found, in priority order.
APP_DIRS = [
    Path.home() / ".local/share/applications",
    Path.home() / ".local/share/flatpak/exports/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path("/var/lib/snapd/desktop/applications"),
    Path("/usr/local/share/applications"),
    Path("/usr/share/applications"),
]


@dataclass
class Group:
    name: str
    apps: list[str]


@dataclass
class Config:
    groups: list[Group]
    metrics: Metrics = field(default_factory=Metrics)
    arrangement: str = "row"


def load_config(path: Path) -> Config:
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)

    settings = raw.get("settings", {})
    metric_fields = set(Metrics.__dataclass_fields__)
    metrics = Metrics(**{k: v for k, v in settings.items() if k in metric_fields})

    groups = [Group(name=g["name"], apps=list(g.get("apps", [])))
              for g in raw.get("group", [])]
    if not groups:
        raise ValueError(f"{path} defines no [[group]] entries")

    return Config(groups=groups, metrics=metrics,
                  arrangement=settings.get("arrangement", "row"))


def resolve_launcher(app_id: str) -> Path | None:
    """Find an installed .desktop file by its id (with or without extension)."""
    name = app_id if app_id.endswith(".desktop") else f"{app_id}.desktop"
    for directory in APP_DIRS:
        candidate = directory / name
        if candidate.exists():
            return candidate
    return None


def resolve_group(group: Group) -> tuple[list[str], list[str]]:
    """Return (launcher urls, missing app ids) for one group."""
    urls, missing = [], []
    for app in group.apps:
        source = resolve_launcher(app)
        if source is None:
            missing.append(app)
        else:
            # Deliberately NOT resolve(): flatpak's exports directory is a
            # symlink farm into content-addressed paths, so resolving would
            # bake in a commit hash that changes on the next app update.
            urls.append(source.as_uri())
    return urls, missing


def read_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def write_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def apply(cfg: Config, dry_run: bool = False) -> None:
    screen = plasma.screen_geometry()
    resolution = f"{screen[0]}x{screen[1]}"

    resolved: list[tuple[Group, list[str]]] = []
    problems: list[str] = []
    for group in cfg.groups:
        urls, missing = resolve_group(group)
        resolved.append((group, urls))
        problems += [f"{group.name}/{m}" for m in missing]

    counts = [(g.name, len(urls)) for g, urls in resolved]
    boxes = solve(counts, screen, cfg.metrics, cfg.arrangement)

    print(f"Screen {resolution}, arrangement {cfg.arrangement!r}")
    for box, (_, urls) in zip(boxes, resolved):
        print(f"  {box.name:<20} {len(urls):>2} apps   {box.x},{box.y}  {box.w}x{box.h}  {box.rows} row(s)")
    for item in problems:
        print(f"  !! not installed: {item}")
    if dry_run:
        print("\n(dry run, nothing changed)")
        return

    state = read_state()
    if state.get("widgets"):
        print("\nRemoving previously created groups")
        plasma.remove_widgets([w["id"] for w in state["widgets"]])

    print("Creating widgets")
    ids = plasma.add_quicklaunch_widgets(
        [(g.name, urls, box.rows) for (g, urls), box in zip(resolved, boxes)]
    )
    containment = plasma.desktop_containment()

    geometry = plasma.format_geometries(
        [(ids[b.name], b.x, b.y, b.w, b.h) for b in boxes]
    )

    print("Positioning (restarting plasmashell)")
    plasma.stop()
    plasma.write_item_geometries(containment, resolution, geometry)
    plasma.start()

    state.update({
        "containment": containment,
        "resolution": resolution,
        "widgets": [{"name": n, "id": i} for n, i in ids.items()],
    })
    write_state(state)
    print(f"\nDone. {len(ids)} groups placed.")


def remove() -> None:
    state = read_state()
    widgets = state.get("widgets", [])
    if not widgets:
        print("No groups recorded in state; nothing to remove.")
        return
    removed = plasma.remove_widgets([w["id"] for w in widgets])
    print(f"Removed {removed} widgets")
    state["widgets"] = []
    write_state(state)


def discover(desktop_dir: Path) -> str:
    """Emit a starter config from whatever launchers are already on the desktop."""
    entries = sorted(p.stem for p in desktop_dir.glob("*.desktop"))
    lines = [
        "# Generated by `paddocks discover`.",
        "# Split these into meaningful [[group]] blocks before applying.",
        "",
        "[settings]",
        'arrangement = "row"',
        "",
        "[[group]]",
        'name = "Apps"',
        "apps = [",
    ]
    lines += [f'    "{e}",' for e in entries]
    lines.append("]")
    return "\n".join(lines) + "\n"
