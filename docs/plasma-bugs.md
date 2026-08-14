<!--
SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>

SPDX-License-Identifier: MIT
-->

# Plasma bug reports drafted from the Paddocks README

Seven reports out of the five findings in the README's "The five things that cost
an afternoon", which decompose into defects and separate wishlists. This is the
drafting copy; as each one goes up at https://bugs.kde.org its number is recorded
below, so the README's findings and the upstream reports stay linked.

Shared version block (paste into every report):

```
Operating System: Ubuntu 26.04 LTS (Kubuntu)
KDE Plasma Version: 6.6.6
KDE Frameworks Version: 6.24.0
Qt Version: 6.10.2
Graphics Platform: Wayland
```

Priority order: **3** first (it is a comment on an existing bug, not a new
report), then **4, 1** — then **2, 5**, then **7**. Report **6** is optional; see
the note on it.

Products and components below were checked against Bugzilla on 2026-08-14 and are
exact. Note there is **no `plasma-workspace` product** — the Plasma shell,
including the code that ships in the `plasma-workspace` package, is filed under
`plasmashell`.

| # | Product | Component | Severity | Status |
|---|---|---|---|---|
| 1 | plasmashell | `desktop:/ IOWorker` | normal | **filed — [524242](https://bugs.kde.org/show_bug.cgi?id=524242)**, REPORTED |
| 2 | plasmashell | `Folder View widget` | normal | not filed |
| 3 | — comment on [bug 362511](https://bugs.kde.org/show_bug.cgi?id=362511) — | | | not posted |
| 4 | plasmashell | `general` | normal | not filed |
| 5 | frameworks-ksvg | `General` | minor | not filed |
| 6 | plasmashell | `Theme - Breeze` | minor | optional, see note |
| 7 | plasmashell | `Containment` | wishlist | not filed |

Duplicate searches run at the same time: nothing pre-existing for 1, 2, 4, 5 or
7. Report 4 is **not** a duplicate of [bug 507681](https://bugs.kde.org/show_bug.cgi?id=507681)
("the plasma-apply-desktoptheme cli tool does not work anymore"), which was a
missing KConfigWatcher notify flag, reported in 6.4.3 and fixed in 6.4.5.

---

## 1. `desktop:/` subpaths list correctly but launching is a silent no-op

**Filed 2026-08-14 as [bug 524242](https://bugs.kde.org/show_bug.cgi?id=524242)**
— status REPORTED, assigned to Plasma Bugs List.

**Product:** plasmashell · **Component:** `desktop:/ IOWorker` ("Only for bugs in
the desktop:/ KIO Worker") · **Severity:** normal · **Version:** 6.6.0 (the
nearest the version list offers; the exact 6.6.6 is in the report body)

The component has six bugs in it, all about properties dialogs, symlinks and
drag-and-drop. Nothing on execution — this is not a duplicate.

### SUMMARY

The `desktop:/` KIO worker implements listing for subdirectories of the desktop
folder, but not execution. Launching a `.desktop` file through a `desktop:/`
subpath exits with status 0 and starts nothing. No error is shown, logged, or
returned to the caller.

Because listing works, a Folder View pointed at `desktop:/SomeFolder` renders a
complete, correct-looking grid of applications where every icon is inert.

### STEPS TO REPRODUCE

1. `mkdir ~/Desktop/Apps` and copy a launcher into it:
   `cp /usr/share/applications/org.kde.kcalc.desktop ~/Desktop/Apps/`
2. Confirm the file launches through KIO by its real path:
   `kioclient exec /home/$USER/Desktop/Apps/org.kde.kcalc.desktop`
3. Launch the same file through the `desktop:/` worker:
   `kioclient exec desktop:/Apps/org.kde.kcalc.desktop`
4. Confirm listing works on the same path:
   `kioclient ls desktop:/Apps`

### OBSERVED RESULT

| URL passed to KIO | Result |
|---|---|
| `/home/$USER/Desktop/Apps/org.kde.kcalc.desktop` | launches |
| `desktop:/Apps/org.kde.kcalc.desktop` | exits 0, launches nothing |
| same, after `chmod +x` on the file | exits 0, launches nothing |
| `desktop:/Apps` (listing) | works fine |

Launching succeeds only at the desktop *root* — `desktop:/org.kde.kcalc.desktop`
works. Any subdirectory breaks it.

### EXPECTED RESULT

Either execution works for subpaths as it does at the root, or the attempt fails
loudly with an error the caller can see. Silent success is the harmful part: a
Folder View built on `desktop:/` looks entirely correct and does nothing when
clicked, which is very expensive to diagnose.

### ADDITIONAL INFORMATION

Marking the file executable makes no difference, so this does not appear to be
the `.desktop` trust mechanism. Found while evaluating Folder View as a grouped
launcher panel; the workaround was to abandon Folder View entirely in favour of
`org.kde.plasma.quicklaunch`.

---

## 2. Folder View at a `file://` URL labels `.desktop` files by filename, not `Name=`

**Product:** plasmashell · **Component:** `Folder View widget` · **Severity:** normal

### SUMMARY

A Folder View widget pointed at a plain `file://` directory containing `.desktop`
files renders each entry's *filename* (`org.kicad.pcbnew.desktop`) rather than
its `Name=` field (`PCB Editor`). The same files shown through `desktop:/` are
labelled correctly.

### STEPS TO REPRODUCE

1. `mkdir ~/Desktop/Apps`, copy several launchers into it — `org.kicad.pcbnew.desktop`
   makes the mismatch obvious since the filename and the display name share nothing.
2. Add a Folder View widget, set its location to `file:///home/$USER/Desktop/Apps`.
3. Compare against a Folder View pointed at `desktop:/Apps`.

### OBSERVED RESULT

`file://` shows `org.kicad.pcbnew.desktop`. `desktop:/` shows `PCB Editor`.

### EXPECTED RESULT

Consistent labelling between the two URL schemes.

### ADDITIONAL INFORMATION

**This may be intentional** — withholding `Name=` from untrusted `.desktop` files
is a recognised anti-spoofing measure, and if so this should be closed as
NOTABUG. One observation that argues against that reading: the *icon* from the
same `.desktop` file resolves and renders correctly. A trust boundary that
displays the attacker-controlled icon while suppressing the attacker-controlled
name is not obviously protecting anything, so if this is deliberate the
inconsistency may still be worth a look.

---

## 3. Widget geometry cannot be set from the Plasma scripting API, and fails silently

**Do not file this as a new bug.** It already exists as
[bug 362511, "Allow setting desktop widget geometry using scripting API"](https://bugs.kde.org/show_bug.cgi?id=362511)
— plasmashell / Scripting, CONFIRMED, opened 30 April 2016, last active
12 December 2025.

That bug is live rather than abandoned: Marco Martin confirmed in 2016 that
applet geometry is not exposed to the scripting console and floated passing
position arguments to `addWidget()` instead, and in November 2025 a commenter
noted `SetGeometry` appears to be empty in the source and offered to attempt a
fix.

What it does **not** yet record is the failure mode, which is the expensive part.
Post the rest of this as a comment there.

### The silent-failure detail worth adding

`desktop.addWidget()` works, but there is no working way to position the widget
it returns. The documented-looking form throws, and the form that does not throw
is silently ignored. Reading the property back reports the auto-placed geometry,
which makes it look as though Plasma accepted the value and then overrode it —
rather than never having applied it at all.

### STEPS TO REPRODUCE

Run via `qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript '<script>'`:

```js
var d = desktops()[0];
var w = d.addWidget("org.kde.plasma.quicklaunch");
w.geometry = Qt.rect(40, 40, 520, 420);   // ReferenceError: Qt is not defined
```

then:

```js
var d = desktops()[0];
var w = d.addWidget("org.kde.plasma.quicklaunch");
w.geometry = {x: 40, y: 40, width: 520, height: 420};   // no error
print(w.geometry.x);                                     // not 40
```

### OBSERVED RESULT

- `Qt.rect()` — `ReferenceError: Qt is not defined`. The `Qt` object is not
  exposed in the scripting engine's global scope.
- Object-literal assignment — no error, no effect, and the read-back reports the
  auto-placed position.

The only way to place a widget is to stop plasmashell and hand-write
`ItemGeometries-<W>x<H>` under `[Containments][<id>]` in
`plasma-org.kde.plasma.desktop-appletsrc`, in the undocumented
`Applet-<id>:x,y,w,h,0;` format. That file is rewritten by plasmashell on exit,
so the write has to happen while the shell is stopped.

### EXPECTED RESULT

Either `widget.geometry` is assignable from scripting (ideally with `Qt.rect()`
available, since that is the form the API's shape implies), or the assignment
raises so the caller knows it did not take. Silently discarding the write while
reporting a different value back is the worst of the three outcomes.

### ADDITIONAL INFORMATION

Related, possibly worth splitting out: `evaluateScript` only reliably returns
`print()` output. A bare trailing expression usually comes back as an empty
string, so scripts have to be written to print rather than evaluate.

Layout scripting is the entire basis of desktop-organiser tooling. Without it,
every such tool is pushed into editing `appletsrc` directly — i.e. onto private
format that a point release can change.

---

## 4. `plasma-apply-desktoptheme` reports success while `AutomaticLookAndFeel` silently overrides it

**Product:** plasmashell · **Component:** `general` · **Severity:** normal

`general` is where the other `plasma-apply-*` reports live (bugs 472792, 511377,
507681). There is no dedicated component for these tools.

### SUMMARY

On systems shipping `AutomaticLookAndFeel=true` in `kdeglobals` — Kubuntu among
them — the look-and-feel package re-asserts its own desktop theme after
`plasma-apply-desktoptheme` runs. The command exits 0, prints a success message,
and `plasmarc` records the requested theme, but Plasma continues rendering the
previous one. Nothing anywhere reports the conflict.

### STEPS TO REPRODUCE

1. On a system with `AutomaticLookAndFeel=true` in `~/.config/kdeglobals`
   (default on Kubuntu), create or install a custom desktop theme.
2. `plasma-apply-desktoptheme MyCustomTheme`
3. Observe the exit status and the message.
4. `kreadconfig6 --file plasmarc --group Theme --key name`
5. Look at the actual desktop.

### OBSERVED RESULT

Exit status 0, success reported, `plasmarc` shows `MyCustomTheme`, and the
desktop renders the look-and-feel package's theme. The only observable signal
that the requested theme was discarded is the pixmap cache mtimes:

```
$ ls -la --time-style=+%H:%M:%S ~/.cache/plasma_theme_*.kcache
... 08:38:36 plasma_theme_MyCustomTheme.kcache      # applied here
... 08:40:15 plasma_theme_kubuntu-light.kcache      # still being used
```

### EXPECTED RESULT

One of:

- the command applies the theme and it sticks; or
- the command warns that `AutomaticLookAndFeel` is enabled and the requested
  theme will be overridden by the active look-and-feel package, and exits
  non-zero.

A CLI tool whose entire job is to apply a setting should not report success when
a known, detectable configuration guarantees the setting will be discarded.

### ADDITIONAL INFORMATION

The workaround is to avoid introducing a new theme id at all: copy the active
theme into `~/.local/share/plasma/desktoptheme/` **under its original name** (the
user data dir shadows `/usr/share`) and patch the copy. This has to be done for
both the light and dark variants or the styling disappears when the day/night
schedule flips.

---

## 5. Plasma theme pixmap cache is not invalidated when a theme's files change under the same name

**Product:** frameworks-ksvg · **Component:** `General` · **Severity:** minor

frameworks-ksvg is "Library for complex SVG handling, including support for
dynamic re-coloring, 9-patch images, and disk caching" — the disk caching clause
is this bug. It has a single `General` component. If the cache turns out not to
be KSvg's, the other candidate is the `libplasma` product.

### SUMMARY

`~/.cache/plasma_theme_<name>.kcache` is keyed by theme name only. Editing a
theme's SVG artwork in place — same theme name, changed files — leaves the stale
cache serving the old artwork indefinitely. There is no mtime or content check.

### STEPS TO REPRODUCE

1. Copy a system desktop theme to `~/.local/share/plasma/desktoptheme/<name>/`,
   keeping the original name.
2. Modify one of its `widgets/*.svgz` files.
3. Restart plasmashell.

### OBSERVED RESULT

The old artwork continues to render. Only deleting the cache makes the change
visible:

```
rm -f ~/.cache/plasma_theme_*.kcache ~/.cache/ksvg-elements
```

and the deletion must happen while plasmashell is stopped, or it repopulates
from memory.

### EXPECTED RESULT

The cache entry is invalidated when the underlying theme files change — a
directory mtime check at load would be enough.

### ADDITIONAL INFORMATION

Caching by name is entirely reasonable for the normal case where themes are
immutable packages. It becomes a trap in combination with report #4, whose
workaround *requires* editing a theme in place under its existing name — so the
two together produce a change that is invisible for two separate reasons at once.

---

## 6. `translucent/widgets/background.svgz` is shipped by every theme and referenced by nothing

**Product:** plasmashell · **Component:** `Theme - Breeze` · **Severity:** minor

### SUMMARY

Every desktop theme ships `translucent/widgets/background.svgz`. Nothing appears
to load it. `BasicAppletContainer.qml` selects between
`widgets/translucentbackground` and `widgets/background`; neither path resolves
into the `translucent/` subdirectory.

### STEPS TO REPRODUCE

1. Note the file exists: `ls /usr/share/plasma/desktoptheme/default/translucent/widgets/`
2. Copy the theme to `~/.local/share/plasma/desktoptheme/` under its own name and
   patch `translucent/widgets/background.svgz`.
3. Restart plasmashell with the theme cache cleared.

### OBSERVED RESULT

No visible change anywhere. Patching `widgets/background.svgz` in the same theme
does take effect, so the theme copy and cache clearing are working.

### EXPECTED RESULT

Either the asset is used, or it is dropped from the themes.

### ADDITIONAL INFORMATION

**Consider not filing this one.** It is accurate, but it is a
tidiness report against theme packaging with no user-visible symptom, and the
likely outcome is a shrug. Its actual value is as context inside report #7,
where "the obvious file to patch is inert" is part of why there is no way to do
the thing. If you want to keep your first round of reports strong, fold this
into #7 as an additional note and skip filing it standalone.

---

## 7. [Wishlist] No way to control desktop widget background opacity

**Product:** plasmashell · **Component:** `Containment` ("The main central desktop
area responsible for widget positioning") · **Severity:** wishlist

`BasicAppletContainer.qml` ships in the `plasma-workspace` package at
`/usr/lib/*/qt6/qml/org/kde/plasma/private/containmentlayoutmanager/`, so the
containment layout manager is the right owner.

### SUMMARY

There is no setting, anywhere in Plasma, for the opacity of a desktop widget's
background frame. Desktop widgets always take the `StandardBackground` path in
`BasicAppletContainer.qml`:

```qml
if (effectiveBackgroundHints & TranslucentBackground) return "widgets/translucentbackground";
else if (effectiveBackgroundHints & StandardBackground) return "widgets/background";
```

so the frame is whatever `widgets/background.svgz` draws, at full opacity.

### EXPECTED RESULT

A per-widget or theme-level opacity control for the applet background frame.

### ADDITIONAL INFORMATION

For anyone else looking for the workaround, and because it points at a possible
implementation constraint: the only way found to do this is to shadow the theme
and add an `opacity` attribute to the nine `<g>` elements in
`widgets/background.svgz` — `center`, `top`, `bottom`, `left`, `right` and the
four corners — individually.

Setting `opacity` on the root `<svg>` element does **not** work, because ancestor
opacity is not applied when Qt renders an SVG by element id, which is how KSvg
draws frame parts. That is worth knowing for any implementation of this feature:
it cannot be done by wrapping the rendered frame in a single opacity group.

The `shadow-*` elements should be left opaque so panels still read against a busy
wallpaper.

Note also that `translucent/widgets/background.svgz` exists in every theme and
appears to be referenced by nothing — it is the obvious first thing to patch and
it has no effect (see report #6).
