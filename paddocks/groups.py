"""Building the groups themselves."""

from __future__ import annotations

import difflib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import apps, plasma
from .layout import ALIGNMENTS, ARRANGEMENTS, Metrics, solve

STATE_FILE = plasma.STATE_DIR / "state.json"

TOP_LEVEL_KEYS = {"settings", "group"}
SETTINGS_KEYS = set(Metrics.__dataclass_fields__) | {"arrangement"}
GROUP_KEYS = {"name", "apps"}


@dataclass
class Group:
    name: str
    apps: list[str]


@dataclass
class Config:
    groups: list[Group]
    metrics: Metrics = field(default_factory=Metrics)
    arrangement: str = "row"
    warnings: list[str] = field(default_factory=list)


class ConfigError(ValueError):
    """A problem with the TOML file, phrased for whoever wrote it."""


def load_config(path: Path) -> Config:
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from None

    _reject_unknown(raw, TOP_LEVEL_KEYS, "top-level key", path)

    settings = raw.get("settings", {})
    if not isinstance(settings, dict):
        raise ConfigError(f"{path}: [settings] must be a table")
    _reject_unknown(settings, SETTINGS_KEYS, "setting", path)

    arrangement = settings.get("arrangement", "row")
    _reject_choice(arrangement, ARRANGEMENTS, "arrangement", path)

    metrics = Metrics(**{k: _check_metric(k, v, path)
                         for k, v in settings.items()
                         if k in Metrics.__dataclass_fields__})
    _reject_choice(metrics.align, ALIGNMENTS, "align", path)

    groups = [_load_group(g, i, path)
              for i, g in enumerate(raw.get("group", []))]
    if not groups:
        raise ConfigError(
            f"{path} defines no [[group]] entries. Each group is a [[group]] "
            'block with a name and a list of apps.'
        )

    return Config(groups=groups, metrics=metrics, arrangement=arrangement,
                  warnings=_warnings(groups))


def _load_group(raw: dict, position: int, path: Path) -> Group:
    where = f"{path}: [[group]] #{position + 1}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} is not a table")
    _reject_unknown(raw, GROUP_KEYS, "group key", path)

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"{where} has no name; every group needs `name = \"...\"`")

    app_ids = raw.get("apps", [])
    if not isinstance(app_ids, list) or any(not isinstance(a, str) for a in app_ids):
        raise ConfigError(f"{where} ({name}): `apps` must be a list of strings")

    return Group(name=name.strip(), apps=list(app_ids))


def _warnings(groups: list[Group]) -> list[str]:
    """Things that are legal but almost certainly not what was meant.

    Duplicate names used to be fatal much later on, once the widgets already
    existed, so they are caught here instead.
    """
    problems: list[str] = []

    seen_names: dict[str, int] = {}
    for group in groups:
        key = group.name.casefold()
        seen_names[key] = seen_names.get(key, 0) + 1
    duplicates = sorted(n for n, c in seen_names.items() if c > 1)
    if duplicates:
        raise ConfigError(
            "two groups share a name: "
            + ", ".join(repr(n) for n in duplicates)
            + ". Group names are the widget titles and must be unique."
        )

    owners: dict[str, list[str]] = {}
    for group in groups:
        if not group.apps:
            problems.append(f"{group.name} lists no apps and will be an empty box")
        for app_id in group.apps:
            owners.setdefault(app_id, []).append(group.name)

    for app_id, names in owners.items():
        if len(names) > len(set(names)):
            problems.append(f"{app_id} is listed twice in {names[0]}")
        elif len(names) > 1:
            problems.append(f"{app_id} appears in {len(names)} groups: "
                            + ", ".join(names))
    return problems


def _reject_unknown(table: dict, known: set[str], kind: str, path: Path) -> None:
    for key in table:
        if key in known:
            continue
        near = difflib.get_close_matches(key, sorted(known), n=1, cutoff=0.6)
        hint = f" (did you mean {near[0]!r}?)" if near else \
               f" (known: {', '.join(sorted(known))})"
        raise ConfigError(f"{path}: unknown {kind} {key!r}{hint}")


def _reject_choice(value, choices: tuple[str, ...], key: str, path: Path) -> None:
    if value not in choices:
        raise ConfigError(
            f"{path}: {key} = {value!r} is not one of {', '.join(choices)}"
        )


def _check_metric(key: str, value, path: Path):
    expected = Metrics.__dataclass_fields__[key].type
    want_int = "int" in str(expected)
    if want_int and (isinstance(value, bool) or not isinstance(value, int)):
        raise ConfigError(f"{path}: {key} must be a whole number, got {value!r}")
    if not want_int and not isinstance(value, str):
        raise ConfigError(f"{path}: {key} must be a string, got {value!r}")
    return value


def resolve_group(group: Group, index: apps.Index) -> tuple[list[str], list[str], list[str]]:
    """Return (launcher urls, misses, substitutions) for one group."""
    urls, misses, swaps = [], [], []
    for app_id in group.apps:
        entry, how = index.resolve(app_id)
        if entry is None:
            suggestions = index.suggest(app_id)
            hint = f"  (did you mean: {', '.join(suggestions)}?)" if suggestions else ""
            misses.append(f"{group.name}/{app_id}{hint}")
            continue
        if how == "alias":
            swaps.append(f"{group.name}/{app_id} -> {entry.app_id}")
        urls.append(entry.url)
    return urls, misses, swaps


def read_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def write_state(state: dict) -> None:
    plasma.STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _record(state: dict, names: list[str], ids: list[int]) -> None:
    state["widgets"] = [{"name": n, "id": i} for n, i in zip(names, ids)]
    write_state(state)


def apply(cfg: Config, dry_run: bool = False, strict: bool = False) -> None:
    for warning in cfg.warnings:
        print(f"warning: {warning}")

    index = apps.build()
    screen = plasma.screen_geometry()
    resolution = f"{screen[0]}x{screen[1]}"

    resolved: list[tuple[Group, list[str]]] = []
    misses: list[str] = []
    swaps: list[str] = []
    for group in cfg.groups:
        urls, group_misses, group_swaps = resolve_group(group, index)
        resolved.append((group, urls))
        misses += group_misses
        swaps += group_swaps

    counts = [(g.name, len(urls)) for g, urls in resolved]
    boxes = solve(counts, screen, cfg.metrics, cfg.arrangement)

    print(f"Screen {resolution}, arrangement {cfg.arrangement!r}")
    for box, (_, urls) in zip(boxes, resolved):
        print(f"  {box.name:<20} {len(urls):>2} apps   {box.x},{box.y}  {box.w}x{box.h}  {box.rows} row(s)")
    for item in swaps:
        print(f"  ~~ matched by name: {item}")
    for item in misses:
        print(f"  !! not installed: {item}")

    # Checked before anything is torn down, so a strict failure leaves the
    # existing groups exactly as they were.
    if strict and misses:
        raise ValueError(
            f"{len(misses)} launcher(s) did not resolve and --strict is set; "
            "nothing was changed"
        )

    if dry_run:
        print("\n(dry run, nothing changed)")
        return

    state = read_state()
    if state.get("widgets"):
        print("\nRemoving previously created groups")
        plasma.remove_widgets([w["id"] for w in state["widgets"]])
        # Written before the rebuild so a failure halfway cannot leave state
        # pointing at widgets that are already gone.
        _record(state, [], [])

    print("Creating widgets")
    names = [g.name for g, _ in resolved]
    try:
        ids = plasma.add_quicklaunch_widgets(
            [(g.name, urls, box.rows) for (g, urls), box in zip(resolved, boxes)]
        )
    except plasma.WidgetCreationError as exc:
        if exc.ids:
            _record(state, names, exc.ids)
            print(f"{len(exc.ids)} widget(s) were created before the failure and "
                  "have been recorded; `paddocks remove` will clean them up.")
        raise

    state["containment"] = plasma.desktop_containment()
    state["resolution"] = resolution
    _record(state, names, ids)

    geometry = plasma.format_geometries(
        [(applet, b.x, b.y, b.w, b.h) for applet, b in zip(ids, boxes)]
    )

    print("Positioning (restarting plasmashell)")
    plasma.stop()
    backup = plasma.backup_appletsrc()
    plasma.write_item_geometries(state["containment"], resolution, geometry)
    plasma.start()

    print(f"\nDone. {len(ids)} groups placed.")
    if backup:
        print(f"Previous desktop layout backed up to {backup}")


def remove() -> None:
    state = read_state()
    widgets = state.get("widgets", [])
    if not widgets:
        print("No groups recorded in state; nothing to remove.")
        return
    removed = plasma.remove_widgets([w["id"] for w in widgets])
    print(f"Removed {removed} widgets")
    _record(state, [], [])


def discover(desktop_dir: Path | None = None, include_all: bool = False) -> str:
    """Emit a starter config from the applications that are installed.

    Grouped by the `Categories=` field of each launcher, which is roughly the
    grouping the application menu already shows, so the result is something to
    edit down rather than something to build from scratch.
    """
    index = apps.build()
    entries = index.visible()

    if desktop_dir is not None:
        on_desktop = {p.stem for p in desktop_dir.glob("*.desktop")}
        if not on_desktop:
            raise ValueError(f"no .desktop files in {desktop_dir}")
        entries = [e for e in entries if e.app_id in on_desktop]

    grouped: dict[str, list[apps.Entry]] = {}
    for entry in entries:
        name = apps.group_for(entry)
        if not include_all and name in apps.NOISY_GROUPS:
            continue
        grouped.setdefault(name, []).append(entry)

    order = [g for _, g in apps.CATEGORY_GROUPS] + [apps.OTHER_GROUP]
    ordered = [(n, grouped[n]) for n in dict.fromkeys(order) if n in grouped]
    if not ordered:
        raise ValueError("found no applications to put in groups")

    total = sum(len(v) for _, v in ordered)
    source = (f"launchers in {desktop_dir}" if desktop_dir is not None
              else "everything installed")
    lines = [
        "# Generated by `paddocks discover`.",
        f"# {total} applications in {len(ordered)} groups, from {source}.",
        "#",
        "# Cut this down to the apps you actually reach for, then check the",
        "# layout with `paddocks apply --dry-run` before applying it.",
        "",
        "[settings]",
        'arrangement = "row"',
        'align = "center"',
    ]
    for name, group_entries in ordered:
        group_entries.sort(key=lambda e: (e.name.casefold(), e.app_id))
        quoted = [f'    "{e.app_id}",' for e in group_entries]
        width = max(len(q) for q in quoted)
        lines += ["", "[[group]]", f'name = "{name}"', "apps = ["]
        lines += [f"{q:<{width}}  # {e.name}" if e.name else q
                  for q, e in zip(quoted, group_entries)]
        lines.append("]")
    return "\n".join(lines) + "\n"
