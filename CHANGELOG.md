<!--
SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>

SPDX-License-Identifier: MIT
-->

# Changelog

## 1.0.0 — 2026-08-21

First release. Everything before this was the repository's `main` branch, which
is where it was developed in the open between 2026-08-11 and 2026-08-21.

### Groups

- Titled groups of launchers on the Plasma desktop, described in a TOML file and
  built out of stock `org.kde.plasma.quicklaunch` widgets. `apply` rebuilds them,
  `remove` takes them away, `discover` writes a starter config from what is
  installed, and `status` says what is currently set up.
- **Folder groups**: a group with `path` instead of `apps` becomes a Folder View
  onto a real directory, which Plasma keeps up to date live.
- **Multi-monitor**: `screen = N` puts a group on a given Plasma screen, and
  `paddocks screens` lists the screens with their sizes and containment ids.
  Each screen is laid out against its own size and written under its own
  `ItemGeometries-<W>x<H>` key.
- `--strict` (or `strict = true`) turns an unresolved launcher into a refusal
  that changes nothing, rather than a group quietly losing an entry.
- Every `apply` copies `plasma-org.kde.plasma.desktop-appletsrc` into
  `~/.local/state/paddocks/backups/` first, keeping the last five.

### Editor

- `paddocks edit` — a Qt window over the same config: groups, their contents, the
  installed application list, drag to reorder, and a **Screen** picker per group
  naming the monitors Plasma reports. Unresolved ids are kept and marked rather
  than dropped.
- PySide6 (LGPL) rather than PyQt6, behind a `gui` extra, so the command line
  works with no Qt installed at all.

### Theming

- `paddocks translucency <opacity>` patches the applet background frame in a
  shadow copy of the active theme, and `reset` removes it. It patches **both**
  variants a theme ships — `widgets/background` and
  `translucent/widgets/background` — because the second is what a blurred
  compositor actually draws, and shadowing only the first turns the blur off
  without saying so.

### Documentation

- The README's five findings are the other half of the project: undocumented
  Plasma behaviour that fails silently, each one reported upstream and each
  outcome recorded, including the two reports that testing showed were wrong.
  `docs/plasma-bugs.md` is the full record.

### Packaging

- Installable with `pipx install`, console script `paddocks`.
- REUSE-compliant, MIT.
- CI on Python 3.11/3.12/3.13, plus a run with the editor extra and a REUSE
  check.
