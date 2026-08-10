# kde-fences

Fences-style desktop groups for KDE Plasma 6, built out of stock Folder View widgets.

If you came here from Windows looking for [Stardock Fences](https://www.stardock.com/products/fences/)
on Linux: there is no port, and it will not run under Wine — it hooks the Windows
shell directly. Plasma can do most of what you actually used Fences for, but the
pieces are undocumented and several of them fail *silently*. This repo is the
working setup plus, more usefully, the five things that waste an afternoon.

<!-- TODO: add docs/screenshot.png before publishing -->

## What you get

Each group becomes a titled Folder View widget on the desktop, positioned and
sized automatically from a small TOML file.

```toml
[[group]]
name = "Electronics"
apps = ["org.kicad.kicad", "org.kicad.pcbnew", "dk.gqrx.gqrx", "gnuradio-grc"]
```

```
kde-fences discover > ~/.config/kde-fences.toml   # starting point from ~/Desktop
$EDITOR ~/.config/kde-fences.toml                 # split into groups
kde-fences apply --dry-run                        # check the computed layout
kde-fences apply
```

Optionally, more transparent widget backgrounds:

```
kde-fences translucency 0.4      # lower = more transparent
kde-fences translucency reset
```

Undo everything:

```
kde-fences remove --delete-store
kde-fences translucency reset
```

## Feature parity with Fences

| Fences | Here |
|---|---|
| Fences (icon groups) | Folder View widgets ✅ |
| Folder Portals | same thing — a fence is a live view of a folder ✅ |
| Titled panels | custom title per fence ✅ |
| Translucent backgrounds | `translucency` command ✅ (see caveats) |
| Multiple desktop pages | Plasma Activities ✅ (not managed here) |
| Roll-up / collapse a fence | ❌ no equivalent |
| Double-click desktop to hide icons | ❌ no equivalent |
| Auto-sorting rules by file type | ❌ groups are declared, not inferred |

## The five things that cost an afternoon

Written down because none of it is documented and most of it fails without an
error message.

### 1. `file://` makes every launcher show its filename

A Folder View pointed at `file:///home/you/Desktop/Apps` renders
`org.kicad.pcbnew.desktop`, not `PCB Editor`. The icon resolves correctly, which
makes it look like a labelling bug rather than a URL problem.

Only the `desktop:/` KIO worker maps `.desktop` files to their `Name=`. So the
URL must be `desktop:/Apps`, and since that worker maps the desktop folder and
nothing else, the launcher store has to live inside `~/Desktop`. Naming it
`.Fences` keeps it from appearing as a desktop icon.

### 2. Plasma's scripting API cannot position widgets

`desktop.addWidget()` works. Positioning it does not:

```js
widget.geometry = Qt.rect(40, 40, 520, 420);   // ReferenceError: Qt is not defined
widget.geometry = {x: 40, y: 40, ...};         // no error, no effect
```

The object-literal form is the nasty one — it silently does nothing, and reading
`widget.geometry` back afterwards reports the auto-placed position, so it looks
like Plasma overrode your value rather than ignoring it.

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

### 3. `plasma-apply-desktoptheme` can be a no-op

On distros that ship `AutomaticLookAndFeel=true` in `kdeglobals` — Kubuntu among
them — the look-and-feel package re-asserts its own desktop theme. The command
reports success, `plasmarc` shows your theme, and Plasma renders something else
entirely.

The only signal is a cache mtime:

```
$ ls -la --time-style=+%H:%M:%S ~/.cache/plasma_theme_*.kcache
... 08:38:36 plasma_theme_MyCustomTheme.kcache      # applied here
... 08:40:15 plasma_theme_kubuntu-light.kcache      # still being used
```

Fix: don't introduce a new theme id. Copy the active theme into
`~/.local/share/plasma/desktoptheme/` **under its original name** — the user data
dir shadows `/usr/share` — and patch the copy. Do it for the light *and* dark
variants, or the styling vanishes when the day/night schedule flips.

### 4. Theme caches are keyed by theme name

Following on from the above: keeping the name means the pixmap cache keeps
serving the old artwork. Clear it while plasmashell is down.

```
rm -f ~/.cache/plasma_theme_*.kcache ~/.cache/ksvg-elements
```

### 5. `widgets/background` is the applet frame; `translucent/` is dead

There is no opacity setting for widget backgrounds anywhere in Plasma. The frame
is a theme SVG, picked in
[`BasicAppletContainer.qml`](https://invent.kde.org/plasma/plasma-desktop):

```qml
if (effectiveBackgroundHints & TranslucentBackground) return "widgets/translucentbackground";
else if (effectiveBackgroundHints & StandardBackground) return "widgets/background";
```

Desktop widgets take the `StandardBackground` path. `translucent/widgets/background.svgz`
exists in every theme and is referenced by nothing — patching it, which is the
obvious first guess, changes nothing.

To make the frame transparent, add an `opacity` attribute to the nine `<g>`
elements `center`, `top`, `bottom`, `left`, `right`, and the four corners.
Ancestor opacity is not applied when Qt renders an SVG by element id, so putting
it on the root `<svg>` does not work either. Leave the `shadow-*` elements alone
so the fences still read against a busy wallpaper.

Most distro themes are sparse — Kubuntu's are 20K of colours — and fall back to
`default` for artwork, so the file you need to copy and patch usually comes from
`/usr/share/plasma/desktoptheme/default/widgets/background.svgz`.

## Requirements

- KDE Plasma 6 (developed against 6.6)
- Python 3.11+ (for `tomllib`)
- `qdbus6`, `kwriteconfig6`, `kquitapp6` — standard on any Plasma install

## Caveats

**Tested on one machine**: Plasma 6.6.6, Kubuntu 26.04, Wayland, single 3440×1440
screen. Multi-monitor is unhandled — everything targets `screenGeometry(0)` and
the containment returned by `desktops()[0]`.

**This leans on private API.** `ItemGeometries` and the containment layout
internals are not a stable interface. A Plasma point release can change the
format; if fences land in the wrong place after an update, that is the first
thing to check.

**Folder View has a minimum size** of roughly 400×304. Groups of one or two items
come out larger than they need to be, and there is no way around it.

**`translucency` shadows system themes.** While the shadow copies exist, distro
updates to those themes stop reaching you. It is a separate command from the
fences for exactly this reason — skip it if that trade is not worth it, and
`translucency reset` removes the copies.

**`apply` rewrites, it does not merge.** It removes the fences it created
previously (tracked in `~/.local/state/kde-fences/state.json`) and rebuilds from
the config. Widgets you placed by hand are left alone, but they are not moved out
of the way either.

## Contributing

Reports from other distros are the most useful thing — particularly whether
`AutomaticLookAndFeel` behaves the same way, and whether the layout constants in
`kdefences/layout.py` hold at other icon sizes and scale factors.

## License

MIT
