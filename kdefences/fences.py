"""Building the fences themselves."""

from __future__ import annotations

import json
import os
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import plasma
from .layout import Metrics, solve

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "kde-fences"
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
    desktop_dir: Path = field(default_factory=lambda: Path.home() / "Desktop")
    store: str = ".Fences"

    @property
    def store_path(self) -> Path:
        # Resolved, not joined: Path.parents is purely lexical, so an unresolved
        # "../elsewhere" would still look like a child of desktop_dir.
        return (self.desktop_dir / self.store).resolve()


def load_config(path: Path) -> Config:
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)

    settings = raw.get("settings", {})
    metric_fields = {f for f in Metrics.__dataclass_fields__}
    metrics = Metrics(**{k: v for k, v in settings.items() if k in metric_fields})

    desktop_dir = Path(settings.get("desktop_dir", "~/Desktop")).expanduser().resolve()
    store = settings.get("store", ".Fences")

    groups = [Group(name=g["name"], apps=list(g.get("apps", [])))
              for g in raw.get("group", [])]
    if not groups:
        raise ValueError(f"{path} defines no [[group]] entries")

    cfg = Config(groups=groups, metrics=metrics,
                 arrangement=settings.get("arrangement", "row"),
                 desktop_dir=desktop_dir, store=store)

    # The desktop: KIO worker only maps the desktop folder. A store outside it
    # would work, but every launcher would show as "org.kde.kate.desktop".
    if cfg.desktop_dir not in cfg.store_path.parents:
        raise ValueError("store must live inside desktop_dir for desktop:/ URLs to resolve")
    return cfg


def resolve_launcher(app_id: str) -> Path | None:
    """Find a .desktop file by its id (with or without the extension)."""
    name = app_id if app_id.endswith(".desktop") else f"{app_id}.desktop"
    for directory in APP_DIRS:
        candidate = directory / name
        if candidate.exists():
            return candidate
    return None


def build_store(cfg: Config, verbose: bool = True) -> tuple[int, list[str]]:
    """Create the group folders and symlink each group's launchers in."""
    linked, missing = 0, []
    cfg.store_path.mkdir(parents=True, exist_ok=True)
    for group in cfg.groups:
        folder = cfg.store_path / group.name
        folder.mkdir(exist_ok=True)
        for app in group.apps:
            source = resolve_launcher(app)
            if source is None:
                missing.append(f"{group.name}/{app}")
                continue
            link = folder / source.name
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(source)
            linked += 1
            if verbose:
                print(f"  {group.name}/{source.name}")
    return linked, missing


def desktop_url(cfg: Config, group: Group) -> str:
    relative = (cfg.store_path / group.name).relative_to(cfg.desktop_dir)
    return f"desktop:/{relative}"


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
    counts = [(g.name, len(g.apps)) for g in cfg.groups]
    boxes = solve(counts, screen, cfg.metrics, cfg.arrangement)

    print(f"Screen {resolution}, arrangement {cfg.arrangement!r}")
    for box in boxes:
        print(f"  {box.name:<20} {box.x},{box.y}  {box.w}x{box.h}")
    if dry_run:
        print("\n(dry run, nothing changed)")
        return

    print("\nLinking launchers:")
    linked, missing = build_store(cfg)
    print(f"  {linked} linked")
    for item in missing:
        print(f"  !! not found: {item}")

    state = read_state()
    if state.get("widgets"):
        print("\nRemoving previously created fences")
        plasma.remove_widgets([w["id"] for w in state["widgets"]])

    print("Creating widgets")
    ids = plasma.add_folder_widgets(
        [(g.name, desktop_url(cfg, g)) for g in cfg.groups]
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
        "store": str(cfg.store_path),
        "widgets": [{"name": n, "id": i} for n, i in ids.items()],
    })
    write_state(state)
    print(f"\nDone. {len(ids)} fences placed.")


def remove(delete_store: bool = False) -> None:
    state = read_state()
    widgets = state.get("widgets", [])
    if not widgets:
        print("No fences recorded in state; nothing to remove.")
    else:
        removed = plasma.remove_widgets([w["id"] for w in widgets])
        print(f"Removed {removed} widgets")
        state["widgets"] = []
        write_state(state)

    store = state.get("store")
    if delete_store and store and Path(store).exists():
        shutil.rmtree(store)
        print(f"Deleted {store}")
    elif store:
        print(f"Launcher store left at {store} (pass --delete-store to remove)")


def discover(desktop_dir: Path) -> str:
    """Emit a starter config from whatever is already on the desktop."""
    entries = sorted(p.stem for p in desktop_dir.glob("*.desktop"))
    lines = [
        "# Generated by `kde-fences discover`.",
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
