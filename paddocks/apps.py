"""Finding installed applications.

Two jobs share one index of the system's ``.desktop`` files: turning the app
ids in a config into launcher paths, and generating a starter config.

Ids in the wild are messier than they look. The same browser is ``firefox``
from a distro package, ``firefox_firefox`` from a snap and
``org.mozilla.firefox`` from a flatpak, so an exact-stem lookup sends the user
hunting through /usr/share/applications for the spelling. We index the obvious
aliases as well, and when there is still no match we suggest the nearest ids
rather than reporting a bare "not installed".
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

# Where .desktop files are found, in priority order.
APP_DIRS = [
    Path.home() / ".local/share/applications",
    Path.home() / ".local/share/flatpak/exports/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path("/var/lib/snapd/desktop/applications"),
    Path("/usr/local/share/applications"),
    Path("/usr/share/applications"),
]

# First matching main category wins, so every app lands in exactly one group.
# Order matters: Steam is "Network;FileTransfer;Game" and belongs under Games,
# KiCad is "Development;Electronics" and belongs under Development.
CATEGORY_GROUPS = [
    ("Development", "Development"),
    ("Game", "Games"),
    ("Graphics", "Graphics"),
    ("AudioVideo", "Media"),
    ("Audio", "Media"),
    ("Video", "Media"),
    ("Office", "Office"),
    ("Network", "Internet"),
    ("Science", "Science"),
    ("Education", "Education"),
    ("Utility", "Utilities"),
    ("System", "System"),
    ("Settings", "Settings"),
]

# Control-panel modules and service entries. Hundreds of them, and nobody wants
# a desktop group of them, so `discover` leaves them out unless asked.
NOISY_GROUPS = {"System", "Settings"}

OTHER_GROUP = "Other"

_WANTED_KEYS = ("Name", "Icon", "Categories", "NoDisplay", "Hidden", "Type",
                "OnlyShowIn", "NotShowIn")


@dataclass(frozen=True)
class Entry:
    app_id: str
    path: Path
    name: str
    icon: str
    categories: tuple[str, ...]
    visible: bool

    @property
    def url(self) -> str:
        # Deliberately NOT resolve(): flatpak's exports directory is a symlink
        # farm into content-addressed paths, so resolving would bake in a
        # commit hash that changes on the next app update.
        return self.path.as_uri()


@dataclass
class Index:
    """All installed launchers, keyed by desktop id."""

    entries: dict[str, Entry] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)

    def resolve(self, app_id: str) -> tuple[Entry | None, str]:
        """Look up one config id. Returns (entry, how) where how is
        "exact", "alias" or "" for a miss."""
        stem = app_id[:-len(".desktop")] if app_id.endswith(".desktop") else app_id

        entry = self.entries.get(stem)
        if entry is not None:
            return entry, "exact"

        alias = self.aliases.get(stem.lower())
        if alias is not None:
            return self.entries[alias], "alias"

        return None, ""

    def suggest(self, app_id: str, count: int = 3) -> list[str]:
        """Desktop ids that look like a typo of `app_id`."""
        stem = app_id[:-len(".desktop")] if app_id.endswith(".desktop") else app_id
        needle = stem.lower()
        pool = sorted(set(self.entries) | set(self.aliases))
        matches = difflib.get_close_matches(needle, pool, n=count * 2, cutoff=0.6)
        if not matches:
            # difflib scores on whole-string similarity, so a short query
            # against a long id ("obs" against com.obsproject.Studio) scores
            # near zero however obviously it is the thing meant.
            matches = [p for p in pool if needle in p]
        # Suggestions are things the user can paste into the config, so map any
        # alias hit back to the real desktop id and drop the duplicates.
        seen, out = set(), []
        for match in matches:
            real = match if match in self.entries else self.aliases.get(match)
            if real and real not in seen:
                seen.add(real)
                out.append(real)
        return out[:count]

    def visible(self) -> list[Entry]:
        return [e for e in self.entries.values() if e.visible]


def build(dirs: list[Path] | None = None) -> Index:
    index = Index()
    for directory in dirs or APP_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.desktop")):
            # Earlier directories win, matching how XDG resolves a desktop id.
            if path.stem in index.entries:
                continue
            entry = _read_entry(path)
            if entry is not None:
                index.entries[path.stem] = entry

    # Four passes, best claim to a name first. `krita_brush.desktop` is a
    # hidden file-association entry also called "Krita", and without the
    # ordering it would win the alias "krita" from org.kde.krita on nothing
    # more than alphabetical luck.
    for visible in (True, False):
        for strong in (True, False):
            for app_id, entry in index.entries.items():
                if entry.visible is not visible:
                    continue
                for alias in _aliases(entry, strong):
                    index.aliases.setdefault(alias, app_id)
    return index


def group_for(entry: Entry) -> str:
    for category, group in CATEGORY_GROUPS:
        if category in entry.categories:
            return group
    return OTHER_GROUP


def _aliases(entry: Entry, strong: bool) -> set[str]:
    """The other names a user might reasonably write for this launcher.

    Weak aliases are the ones that guess at structure inside the id, so they
    only get to claim a name once every unambiguous reading of it is taken.
    """
    app_id = entry.app_id
    out: set[str] = set()

    if strong:
        out.add(app_id.lower())
        # Reverse-DNS ids: org.kde.krita -> krita
        if "." in app_id:
            out.add(app_id.rsplit(".", 1)[-1].lower())
        if entry.name:
            name = entry.name.lower()
            out.update({name, name.replace(" ", ""), name.replace(" ", "-")})
    else:
        # Snap ids: firefox_firefox -> firefox. Also splits ids that merely
        # contain an underscore, hence weak.
        out.update(part.lower() for part in app_id.split("_"))

    out.discard("")
    return out


def _read_entry(path: Path) -> Entry | None:
    data = _parse(path)
    if data is None:
        return None

    categories = tuple(c for c in data.get("Categories", "").split(";") if c)
    return Entry(
        app_id=path.stem,
        path=path,
        name=data.get("Name", "").strip(),
        icon=data.get("Icon", "").strip(),
        categories=categories,
        visible=_is_visible(data),
    )


def _is_visible(data: dict[str, str]) -> bool:
    if data.get("Type", "Application") != "Application":
        return False
    if data.get("NoDisplay", "").lower() == "true":
        return False
    if data.get("Hidden", "").lower() == "true":
        return False
    only = data.get("OnlyShowIn")
    if only and "KDE" not in only.split(";"):
        return False
    if "KDE" in data.get("NotShowIn", "").split(";"):
        return False
    return True


def _parse(path: Path) -> dict[str, str] | None:
    """Read the [Desktop Entry] group. Localised keys (Name[de]) are ignored."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    data: dict[str, str] = {}
    in_entry = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            if in_entry:
                break
            in_entry = line == "[Desktop Entry]"
            continue
        if not in_entry or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in _WANTED_KEYS:
            data.setdefault(key, value.strip())
    return data if in_entry else None
