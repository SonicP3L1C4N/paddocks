"""Optional: make applet backgrounds more transparent.

This is the fragile half of the project and is deliberately separate from the
groups. There is no setting for widget background opacity anywhere in Plasma
-- the frame is painted from the desktop theme's ``widgets/background`` SVG
(see BasicAppletContainer.qml in plasma-workspace), so the only way to change
it is to edit that artwork.

Two traps live here:

1. Distros with ``AutomaticLookAndFeel=true`` (Kubuntu among them) let the
   look-and-feel package re-assert its own desktop theme, which silently
   overrides anything ``plasma-apply-desktoptheme`` wrote into plasmarc.
   Applying a brand new custom theme therefore appears to do nothing at all.
   We sidestep it by shadowing the *active* theme under its own id in
   ~/.local/share, which takes priority over /usr/share.
2. Theme pixmap caches are keyed by theme name. Since we keep the name, the
   cache must be cleared or Plasma serves the old artwork forever.
"""

from __future__ import annotations

import gzip
import re
import shutil
from pathlib import Path

from . import plasma

FRAME_ELEMENTS = ("center", "top", "bottom", "left", "right",
                  "topleft", "topright", "bottomleft", "bottomright")

USER_THEMES = Path.home() / ".local/share/plasma/desktoptheme"
SYSTEM_THEME_DIRS = [Path("/usr/local/share/plasma/desktoptheme"),
                     Path("/usr/share/plasma/desktoptheme")]

_G_TAG = re.compile(r'<g[^>]*?\bid="([^"]+)"[^>]*>')


def active_themes() -> list[str]:
    """Themes that actually get rendered, including the light/dark counterpart.

    plasmarc is not authoritative when a look-and-feel package is driving the
    theme, so we read the package's `contents/defaults` too.
    """
    names: list[str] = []

    plasmarc = plasma.CONFIG_DIR / "plasmarc"
    if plasmarc.exists():
        match = re.search(r"^\[Theme\]\s*$.*?^name=(.+?)$",
                          plasmarc.read_text(), re.M | re.S)
        if match:
            names.append(match.group(1).strip())

    kdeglobals = plasma.CONFIG_DIR / "kdeglobals"
    if kdeglobals.exists():
        match = re.search(r"^LookAndFeelPackage=(.+?)$", kdeglobals.read_text(), re.M)
        if match:
            names += _themes_from_lookandfeel(match.group(1).strip())

    # A light theme is usually paired with a dark one that gets swapped in on a
    # schedule; patch both so the look does not change halfway through the day.
    for name in list(names):
        for a, b in (("-light", "-dark"), ("-dark", "-light")):
            if name.endswith(a):
                names.append(name[: -len(a)] + b)

    seen, result = set(), []
    for name in names:
        if _is_safe_name(name) and name not in seen and _system_theme_dir(name):
            seen.add(name)
            result.append(name)
    return result


def _is_safe_name(name: str) -> bool:
    """A theme id names one directory; it is not a path.

    Worth enforcing rather than assuming. These names arrive from plasmarc and
    from look-and-feel packages, and look-and-feel packages are routinely
    installed from the KDE Store -- third-party content with no business
    steering a copytree or an rmtree out of the theme directory. Without this,
    a name of ``../../../../../../tmp/x`` passes the is_dir() check below
    (because the traversal resolves to somewhere that does exist) and
    ``reset()`` deletes whatever it lands on.
    """
    return bool(name) and name not in (".", "..") \
        and not any(c in name for c in ("/", "\\", "\0"))


def _themes_from_lookandfeel(package: str) -> list[str]:
    for base in [Path.home() / ".local/share/plasma/look-and-feel"] + \
                [Path("/usr/share/plasma/look-and-feel")]:
        defaults = base / package / "contents" / "defaults"
        if defaults.exists():
            match = re.search(r"^\[plasmarc\]\[Theme\]\s*$\s*^name=(.+?)$",
                              defaults.read_text(), re.M)
            if match:
                return [match.group(1).strip()]
    return []


def _system_theme_dir(name: str) -> Path | None:
    if not _is_safe_name(name):
        return None
    for base in SYSTEM_THEME_DIRS:
        if (base / name).is_dir():
            return base / name
    return None


def _source_background(theme: str) -> Path:
    """Pristine artwork for a theme, never our own patched copy.

    Most distro themes are sparse -- they ship colours and fall back to
    `default` for everything else -- so the asset usually comes from there.
    """
    for name in (theme, "default", "breeze"):
        directory = _system_theme_dir(name)
        if not directory:
            continue
        for candidate in (directory / "widgets/background.svgz",
                          directory / "widgets/background.svg"):
            if candidate.exists():
                return candidate
    raise RuntimeError("could not find a source widgets/background asset")


def _patch_svg(data: str, opacity: float) -> tuple[str, int]:
    patched = 0

    def replace(match: re.Match) -> str:
        nonlocal patched
        tag, element = match.group(0), match.group(1)
        if element not in FRAME_ELEMENTS or "opacity=" in tag:
            return tag
        patched += 1
        return tag[:-1].rstrip() + f' opacity="{opacity}">'

    return _G_TAG.sub(replace, data), patched


def _read(path: Path) -> str:
    if path.suffix == ".svgz":
        return gzip.open(path).read().decode()
    return path.read_text()


def apply(opacity: float, restart: bool = True) -> list[str]:
    if not 0.0 < opacity <= 1.0:
        raise ValueError("opacity must be between 0 and 1")

    themes = active_themes()
    if not themes:
        raise RuntimeError("could not determine the active desktop theme")

    touched = []
    for theme in themes:
        source = _source_background(theme)
        patched, count = _patch_svg(_read(source), opacity)
        if count == 0:
            raise RuntimeError(f"no frame elements found in {source}")

        target_dir = USER_THEMES / theme
        if not target_dir.exists():
            shutil.copytree(_system_theme_dir(theme), target_dir)
            for item in target_dir.rglob("*"):
                item.chmod(item.stat().st_mode | 0o200)

        widgets = target_dir / "widgets"
        widgets.mkdir(parents=True, exist_ok=True)
        with gzip.open(widgets / "background.svgz", "wb", compresslevel=9) as fh:
            fh.write(patched.encode())
        # A plain .svg alongside would win over our .svgz.
        (widgets / "background.svg").unlink(missing_ok=True)
        touched.append(theme)

    _reload(restart)
    return touched


def reset(restart: bool = True) -> list[str]:
    """Drop the shadow themes so the distro's originals apply again."""
    removed = []
    for theme in active_themes():
        target = USER_THEMES / theme
        if target.exists():
            shutil.rmtree(target)
            removed.append(theme)
    _reload(restart)
    return removed


def _reload(restart: bool) -> None:
    if not restart:
        return
    plasma.stop()
    # Whatever goes wrong in between, the user gets their desktop shell back.
    try:
        plasma.clear_theme_caches()
    finally:
        plasma.start()
