# Paddocks

Grouped desktop launcher panels for KDE Plasma 6, built out of stock Plasma widgets.

Windows has several tools that group desktop icons into titled, translucent
panels. Linux has none of them — the best known is Windows-only and will not run
under Wine, because it hooks the Windows shell directly. Plasma can already do
most of what those tools are used for, but the pieces are undocumented and
several of them fail *silently*.

Paddocks is the working setup, plus — more usefully — the five things that
otherwise cost an afternoon each.

![Six groups laid out across the top of a 3440x1440 desktop](docs/screenshot.png)

## What you get

Each group becomes a titled Quicklaunch widget on the desktop, positioned and
sized automatically from a small TOML file.

```toml
[[group]]
name = "Electronics"
apps = ["org.kicad.kicad", "org.kicad.pcbnew", "dk.gqrx.gqrx", "gnuradio-grc"]
```

![A single group close up: custom title, application names, translucent background](docs/detail.png)

Launchers show their application name, each group carries its own title, and
the panel background is optionally translucent. Clicking launches; dragging an
application onto a group adds it.

```
paddocks discover > ~/.config/paddocks.toml   # every installed app, pre-grouped
$EDITOR ~/.config/paddocks.toml               # cut it down to what you use
paddocks apply --dry-run                      # check the computed layout
paddocks apply
```

`discover` reads every installed `.desktop` file and buckets it by the
`Categories=` field, which is roughly the grouping the application menu already
shows, and annotates each id with the application name so the config is
editable without looking anything up:

```toml
[[group]]
name = "Graphics"
apps = [
    "org.blender.Blender",   # Blender
    "org.inkscape.Inkscape", # Inkscape
    "org.kde.krita",         # Krita
]
```

That is deliberately more than fits on a screen — it is a list to delete from.
`--desktop-only` narrows it to apps that already have a launcher in `~/Desktop`,
and `--all` adds the System and Settings entries that are otherwise left out.

### App ids

Ids do not have to be the exact `.desktop` filename. The same application is
`firefox` from a distro package, `firefox_firefox` from a snap and
`org.mozilla.firefox` from a flatpak, so `apps` entries are also matched against
the reverse-DNS tail, the snap-style suffix, and the launcher's `Name=`. A match
that was not exact is reported, so you can tighten the config if you want to:

```
~~ matched by name: Office and Web/firefox -> firefox_firefox
```

An id that resolves to nothing is reported with the nearest candidates and
skipped, and the group is built without it:

```
!! not installed: Dev Tools/vscode  (did you mean: code, discord?)
```

Pass `--strict` to make that an error instead — useful once a config is settled,
or when driving `apply` from a script:

```
paddocks apply --strict        # exits 1, changes nothing, if any id is missing
```

Optionally, more transparent widget backgrounds:

```
paddocks translucency 0.4      # lower = more transparent
paddocks translucency reset
```

Undo everything:

```
paddocks remove
paddocks translucency reset
```

## Install

No packaging yet — clone and symlink the entry point onto your PATH.

```
git clone https://github.com/SonicP3L1C4N/paddocks.git
ln -s "$PWD/paddocks/bin/paddocks" ~/.local/bin/paddocks
```

Requires KDE Plasma 6 (developed against 6.6), Python 3.11+ for `tomllib`, and
`qdbus6` / `kwriteconfig6` / `kquitapp6`, all standard on a Plasma install.

## What it does and does not cover

| Capability | Status |
|---|---|
| Grouped, titled launcher panels | ✅ |
| Click to launch, drag to add | ✅ |
| Translucent backgrounds | ✅ see caveats |
| Arbitrary files and folders in a group | ❌ launchers only |
| Multiple desktop pages | ✅ use Plasma Activities (not managed here) |
| Roll-up / collapse a panel | ❌ no equivalent in Plasma |
| Double-click desktop to hide icons | ❌ no equivalent |
| Auto-sorting rules by file type | ❌ groups are declared, not inferred |

## The five things that cost an afternoon

None of this is documented, and most of it fails without an error message.

### 1. Folder View looks like the right widget, and is a dead end

The obvious way to build this is a Folder View widget per group, pointed at a
folder of `.desktop` files. Both available URL schemes fail, in different ways:

* **`file:///home/you/Desktop/Apps`** — renders `org.kicad.pcbnew.desktop`
  instead of `PCB Editor`. The *icon* resolves correctly, so it reads as a
  labelling bug rather than a URL problem. Only the `desktop:/` KIO worker maps
  `.desktop` files to their `Name=`.
* **`desktop:/Apps`** — labels are correct, and it looks like the answer. But
  `kio_desktop` only implements part of the protocol for subpaths. Listing works;
  **launching is a silent no-op and file changes are never noticed**. Click an
  icon and nothing happens, with nothing logged. Drop a new launcher in and the
  widget never shows it, though the file lands on disk.

That second failure is worth spelling out, because it costs a day to trust and
then unpick. Verified with `kioclient exec`:

| URL passed to KIO | Result |
|---|---|
| `/home/you/Desktop/Apps/kcalc.desktop` | launches |
| `desktop:/Apps/kcalc.desktop` | exits 0, launches nothing |
| same, file made executable | exits 0, launches nothing |
| `desktop:/Apps` (listing) | works fine |

Launching only works at the desktop *root* — any grouping folder breaks it. So
the trade is: correct labels or working launchers, never both.

**Use Quicklaunch instead.** `org.kde.plasma.quicklaunch` stores `file://` URLs
pointing straight at installed `.desktop` files, renders them by application
name, launches them, and accepts drag-and-drop. It is the right widget for
grouping launchers; Folder View is the right widget for showing a folder.

One non-obvious key: set `maxSectionCount` to the number of icon rows you want.
Without it Quicklaunch flows every launcher into a single row and shrinks the
icons to fit, so icon size ends up varying from group to group.

A second, subtler one: Quicklaunch *balances* icons across the rows it is given,
so six icons in two rows render 3+3 rather than 4+2. Size the widget to that
balanced column count. Size it to the maximum instead and Quicklaunch scales the
icons up to fill the extra width, leaving every group a slightly different icon
size — which reads as sloppy without being obviously wrong.

### 2. Plasma's scripting API cannot position widgets

`desktop.addWidget()` works. Positioning it does not:

```js
widget.geometry = Qt.rect(40, 40, 520, 420);   // ReferenceError: Qt is not defined
widget.geometry = {x: 40, y: 40, ...};         // no error, no effect
```

The object-literal form is the nasty one — it silently does nothing, and reading
`widget.geometry` back reports the auto-placed position, so it looks like Plasma
overrode your value rather than ignoring it.

Positions live in `ItemGeometries-<W>x<H>` under `[Containments][<id>]` in
`~/.config/plasma-org.kde.plasma.desktop-appletsrc`, formatted
`Applet-<id>:x,y,w,h,0;`. **plasmashell rewrites that file when it exits**, so it
must be stopped before the write, not after:

```
kquitapp6 plasmashell
kwriteconfig6 --file plasma-org.kde.plasma.desktop-appletsrc \
  --group Containments --group 1 --key ItemGeometries-3440x1440 "Applet-28:60,50,560,336,0;"
plasmashell &
```

Also note `evaluateScript` only reliably returns `print()` output — a bare
trailing expression usually comes back empty.

### 3. `plasma-apply-desktoptheme` can be a silent no-op

On distros shipping `AutomaticLookAndFeel=true` in `kdeglobals` — Kubuntu among
them — the look-and-feel package re-asserts its own desktop theme. The command
reports success, `plasmarc` shows your theme, and Plasma renders something else.

The only signal is a cache mtime:

```
$ ls -la --time-style=+%H:%M:%S ~/.cache/plasma_theme_*.kcache
... 08:38:36 plasma_theme_MyCustomTheme.kcache      # applied here
... 08:40:15 plasma_theme_kubuntu-light.kcache      # still being used
```

Fix: don't introduce a new theme id at all. Copy the active theme into
`~/.local/share/plasma/desktoptheme/` **under its original name** — the user data
dir shadows `/usr/share` — and patch the copy. Do it for the light *and* dark
variants, or the styling vanishes when the day/night schedule flips.

### 4. Theme caches are keyed by theme name

Following from the above: keeping the name means the pixmap cache keeps serving
the old artwork. Clear it while plasmashell is down.

```
rm -f ~/.cache/plasma_theme_*.kcache ~/.cache/ksvg-elements
```

### 5. `widgets/background` is the applet frame; `translucent/` is dead

There is no opacity setting for widget backgrounds anywhere in Plasma. The frame
is a theme SVG, selected in `BasicAppletContainer.qml`:

```qml
if (effectiveBackgroundHints & TranslucentBackground) return "widgets/translucentbackground";
else if (effectiveBackgroundHints & StandardBackground) return "widgets/background";
```

Desktop widgets take the `StandardBackground` path.
`translucent/widgets/background.svgz` exists in every theme and is referenced by
nothing — patching it, the obvious first guess, changes nothing.

To make the frame transparent, add an `opacity` attribute to the nine `<g>`
elements `center`, `top`, `bottom`, `left`, `right` and the four corners.
Ancestor opacity is not applied when Qt renders an SVG by element id, so setting
it on the root `<svg>` does not work either. Leave the `shadow-*` elements alone
so panels still read against a busy wallpaper.

Most distro themes are sparse — Kubuntu's are 20K of colours — and fall back to
`default` for artwork, so the file to copy and patch is usually
`/usr/share/plasma/desktoptheme/default/widgets/background.svgz`.

## Caveats

**Tested on one machine.** Plasma 6.6.6, Kubuntu 26.04, Wayland, a single
3440×1440 screen. Multi-monitor is unhandled — everything targets
`screenGeometry(0)` and the containment from `desktops()[0]`.

**This leans on private API.** `ItemGeometries` and the containment layout
internals are not a stable interface. A Plasma point release can change the
format; if panels land in the wrong place after an update, check that first.

**Groups hold application launchers, not files.** Quicklaunch is a launcher
widget; if you want a group that holds documents or folders, that is Folder
View's job, with the caveats in gotcha #1.

**`translucency` shadows system themes.** While the shadow copies exist, distro
updates to those themes stop reaching you. That is why it is a separate command
from the groups — skip it if the trade is not worth it. `translucency reset`
removes the copies.

**`apply` rewrites, it does not merge.** It removes the widgets it created
previously (tracked in `~/.local/state/paddocks/state.json`) and rebuilds from
the config. Widgets you placed by hand are left alone, but not moved out of the
way either. Launchers you add by dragging onto a group live in that widget's
config, so `apply` will discard them — add them to the TOML instead.

**Every `apply` backs up your desktop layout first.** `ItemGeometries` lives in
`plasma-org.kde.plasma.desktop-appletsrc`, alongside every panel, widget and
wallpaper setting you have, so the file is copied into
`~/.local/state/paddocks/backups/` before it is touched. The last five are kept.
Restoring one is a copy back, with plasmashell stopped — the same reason the
write itself needs it:

```
kquitapp6 plasmashell
cp ~/.local/state/paddocks/backups/plasma-org.kde.plasma.desktop-appletsrc.<stamp> \
   ~/.config/plasma-org.kde.plasma.desktop-appletsrc
plasmashell &
```

**Do not `resolve()` launcher paths.** Flatpak's `exports/share/applications`
is a symlink farm into content-addressed store paths. Following those symlinks
bakes a commit hash into the URL, and every flatpak launcher breaks on the next
update of that app. Use the export path as-is.

## Contributing

Reports from other distros are the most useful thing — particularly whether
`AutomaticLookAndFeel` behaves the same way, and whether the layout constants in
`paddocks/layout.py` hold at other icon sizes and scale factors.

## Trademarks

Paddocks is an independent project, not affiliated with, endorsed by, or derived
from any commercial desktop-organiser product. Any such products are named only
for factual comparison, and remain the trademarks of their respective owners.

## License

MIT
