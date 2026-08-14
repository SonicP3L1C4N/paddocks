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
| 2 | plasmashell | `Folder View widget` | normal | **filed — [524243](https://bugs.kde.org/show_bug.cgi?id=524243)**, REPORTED |
| 3 | — comment on [bug 362511](https://bugs.kde.org/show_bug.cgi?id=362511) — | | | **posted** as comment #5, 2026-08-14 |
| 4 | plasmashell | `general` | normal | **filed — [524244](https://bugs.kde.org/show_bug.cgi?id=524244)**, REPORTED |
| 5 | frameworks-ksvg | `General` | normal | **filed — [524245](https://bugs.kde.org/show_bug.cgi?id=524245)**, REPORTED |
| 6 | plasmashell | `Theme - Breeze` | minor | **filed — [524246](https://bugs.kde.org/show_bug.cgi?id=524246)**, REPORTED |
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
the desktop:/ KIO Worker") · **Severity:** normal · **Version:** 6.6.6

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

**Filed 2026-08-14 as [bug 524243](https://bugs.kde.org/show_bug.cgi?id=524243)**
— status REPORTED, assigned to Plasma Bugs List.

**Product:** plasmashell · **Component:** `Folder View widget` · **Severity:** normal
· **Version:** 6.6.6

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
Paste the block below as a comment there.

Written as plain text, not the bug template — Bugzilla comments do not render
markdown, and a ten-year-old confirmed report does not need its own request
restated back at it. It opens on what is new, answers the design question raised
in the thread, and closes with an offer to test.

### Comment to post on 362511

```text
Adding a data point from writing a desktop layout tool against this, plus the
failure mode, which I don't think is recorded here yet.

The gap is not only that geometry is unavailable -- it is that both ways of
attempting it fail without saying so.

    var d = desktops()[0];
    var w = d.addWidget("org.kde.plasma.quicklaunch");
    w.geometry = Qt.rect(40, 40, 520, 420);

throws "ReferenceError: Qt is not defined". The Qt object is not exposed in the
scripting engine's global scope, so the form the API's shape implies cannot even
be attempted.

    w.geometry = {x: 40, y: 40, width: 520, height: 420};
    print(w.geometry.x);   // not 40

produces no error at all. The assignment is discarded, and reading the property
back returns the auto-placed position. That read-back is what costs the time: it
looks exactly as though Plasma accepted the value and then re-laid out over the
top of it, so you go hunting for a layout policy to opt out of rather than
concluding the setter is a no-op. It is consistent with the observation above
that SetGeometry appears to be empty.

Even if implementing the setter is not on the cards, having the assignment raise
instead of silently discarding would remove most of the cost here.

On the suggestion above of passing position arguments to addWidget(): as an API
for tools that would only solve half of it. Layout tools re-place widgets that
already exist, not only ones they are creating -- on every config change, and
again when the screen resolution changes, since the ItemGeometries key name
changes with it. Creation-time parameters would still leave "move this widget"
unavailable.

The only route that works today is to stop plasmashell, write
ItemGeometries-<W>x<H> under [Containments][<id>] in
plasma-org.kde.plasma.desktop-appletsrc in the Applet-<id>:x,y,w,h,0; format,
and start the shell again. plasmashell rewrites that file on exit, so the write
cannot happen while it is running. That is a private format behind a shell
restart, for a tool that only wants to position a widget.

Adjacent, in case it saves anyone else the detour: evaluateScript only reliably
returns print() output. A bare trailing expression usually comes back empty.

Operating System: Ubuntu 26.04 LTS (Kubuntu)
KDE Plasma Version: 6.6.6
KDE Frameworks Version: 6.24.0
Qt Version: 6.10.2
Graphics Platform: Wayland

Happy to test a patch against this if one appears.
```

---

## 4. `plasma-apply-desktoptheme` reports success while `AutomaticLookAndFeel` silently overrides it

**Filed 2026-08-14 as [bug 524244](https://bugs.kde.org/show_bug.cgi?id=524244)**
— status REPORTED, assigned to Plasma Bugs List.

**Product:** plasmashell · **Component:** `general` · **Severity:** normal ·
**Version:** 6.6.6

`general` is where the other `plasma-apply-*` reports live (bugs 472792, 511377,
507681). There is no dedicated component for these tools.

The body below is plain text for the same reason as #3 — Bugzilla does not render
markdown. The one framing risk here is being closed as a Kubuntu packaging
problem, so the summary says up front that both the setting and the tool are
KDE's.

### Report body to paste

```text
SUMMARY

On systems with AutomaticLookAndFeel=true in kdeglobals, the active look-and-feel
package re-asserts its own desktop theme after plasma-apply-desktoptheme has run.
The command exits 0 and reports success, and plasmarc records the requested
theme, but Plasma goes on rendering the previous one. Nothing reports the
conflict.

Kubuntu ships AutomaticLookAndFeel=true by default, which is where I hit this,
but the setting and the tool are both KDE's -- any system automatically applying
a look-and-feel package will behave the same way.

STEPS TO REPRODUCE

1. On a system with AutomaticLookAndFeel=true in ~/.config/kdeglobals, install or
   create a custom desktop theme.
2. Run: plasma-apply-desktoptheme MyCustomTheme
3. Note the exit status and the message printed.
4. Run: kreadconfig6 --file plasmarc --group Theme --key name
5. Look at the desktop.

OBSERVED RESULT

Exit status 0, success reported, and plasmarc shows MyCustomTheme -- while the
desktop carries on rendering the look-and-feel package's theme.

The only observable signal that the requested theme was discarded is the pixmap
cache mtimes:

    $ ls -la --time-style=+%H:%M:%S ~/.cache/plasma_theme_*.kcache
    ... 08:38:36 plasma_theme_MyCustomTheme.kcache      # applied here
    ... 08:40:15 plasma_theme_kubuntu-light.kcache      # still being used

EXPECTED RESULT

Either the applied theme sticks, or the tool detects that AutomaticLookAndFeel is
enabled and warns that the requested theme will be overridden by the active
look-and-feel package, exiting non-zero.

A tool whose only job is to apply a setting should not report success when a
detectable configuration guarantees that setting will be discarded. The state it
leaves behind is worse than a plain failure, because plasmarc now disagrees with
the screen -- so the obvious next diagnostic confirms the theme was applied, and
sends you looking anywhere but at the tool.

ADDITIONAL INFORMATION

This is not a duplicate of bug 507681 ("The plasma-apply-desktoptheme cli tool
does not work anymore"), which was a missing KConfigWatcher notify flag, reported
against 6.4.3 and fixed in 6.4.5. Different cause, and still present in 6.6.6.

The workaround, for anyone who lands here: do not introduce a new theme id at
all. Copy the active theme into ~/.local/share/plasma/desktoptheme/ under its
original name -- the user data dir shadows /usr/share -- and patch the copy. It
has to be done for the light and the dark variant both, or the styling vanishes
when the day/night schedule flips.

Operating System: Ubuntu 26.04 LTS (Kubuntu)
KDE Plasma Version: 6.6.6
KDE Frameworks Version: 6.24.0
Qt Version: 6.10.2
Graphics Platform: Wayland
```

---

## 5. Plasma theme pixmap cache is not invalidated when a theme's files change under the same name

**Filed 2026-08-14 as [bug 524245](https://bugs.kde.org/show_bug.cgi?id=524245)**
— status REPORTED, assigned to Plasma Bugs List.

**Product:** frameworks-ksvg · **Component:** `General` · **Severity:** normal ·
**Version:** 6.24.0, the KSvg/Frameworks number — this is a Frameworks product,
not a Plasma one

Drafted as `minor`, filed as `normal`, and `normal` is the better call: stale
artwork is wrong output, not a cosmetic nit. Left as filed.

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

**Filed 2026-08-14 as [bug 524246](https://bugs.kde.org/show_bug.cgi?id=524246)**
— status REPORTED, assigned to Plasma Bugs List.

**Product:** plasmashell · **Component:** `Theme - Breeze` · **Severity:** minor ·
**Version:** 6.6.6

I had drafted this as "probably not worth filing standalone" — a tidiness report
with no user-visible symptom. Filed anyway, which was the better call: it gives
#7 something concrete to cite, and it is verifiable in one command.

**Filed from the pre-conversion markdown draft**, so its ADDITIONAL INFORMATION
section is the drafting note arguing against filing it, rather than report
content. Comment 0 is not editable by the reporter on KDE Bugzilla, so the fix is
the follow-up below. The paste block further down is the corrected version and
was never posted.

### Follow-up comment to post on 524246

```text
The ADDITIONAL INFORMATION paragraph above is a stray note from my drafting file,
about whether to file this at all -- please disregard it, it is not part of the
report.

Two things the description was missing.

Step 3 in full:

    kquitapp6 plasmashell
    rm -f ~/.cache/plasma_theme_*.kcache ~/.cache/ksvg-elements
    plasmashell &

The cache deletion has to happen while the shell is stopped, or it repopulates
from memory. Patching widgets/background.svgz in the same theme copy does take
effect, so the theme shadowing and the cache clearing are both working -- the
translucent/ variant simply is not read.

And why it seemed worth reporting rather than leaving alone: it is the obvious
first file to patch when trying to make applet backgrounds translucent, so the
time it costs is spent before you have any reason to doubt it.

Operating System: Ubuntu 26.04 LTS (Kubuntu)
KDE Plasma Version: 6.6.6
KDE Frameworks Version: 6.24.0
Qt Version: 6.10.2
Graphics Platform: Wayland
```

### Report body to paste

```text
SUMMARY

Every desktop theme ships translucent/widgets/background.svgz. As far as I can
tell, nothing loads it. BasicAppletContainer.qml selects between
"widgets/translucentbackground" and "widgets/background", and neither path
resolves into the translucent/ subdirectory.

STEPS TO REPRODUCE

1. Confirm the file is shipped:

       ls /usr/share/plasma/desktoptheme/default/translucent/widgets/

2. Copy the theme into ~/.local/share/plasma/desktoptheme/ under its own name,
   and patch translucent/widgets/background.svgz with an obvious visible change.

3. Clear the theme cache and restart the shell:

       kquitapp6 plasmashell
       rm -f ~/.cache/plasma_theme_*.kcache ~/.cache/ksvg-elements
       plasmashell &

OBSERVED RESULT

No visible change anywhere.

Patching widgets/background.svgz in the same theme copy does take effect, so the
theme shadowing and the cache clearing are both working -- the translucent/
variant simply is not read.

EXPECTED RESULT

Either the asset is used for something, or it is dropped from the themes.

As it stands it is the obvious first thing to patch when trying to make applet
backgrounds translucent, and patching it does nothing at all, which costs a
while to work out.

Operating System: Ubuntu 26.04 LTS (Kubuntu)
KDE Plasma Version: 6.6.6
KDE Frameworks Version: 6.24.0
Qt Version: 6.10.2
Graphics Platform: Wayland
```

---

## 7. [Wishlist] No way to control desktop widget background opacity

**Product:** plasmashell · **Component:** `Containment` ("The main central desktop
area responsible for widget positioning") · **Severity:** wishlist

`BasicAppletContainer.qml` ships in the `plasma-workspace` package at
`/usr/lib/*/qt6/qml/org/kde/plasma/private/containmentlayoutmanager/`, so the
containment layout manager is the right owner.

**Suggested title:** `No way to control the opacity of a desktop widget's background frame`

The only wishlist in the set, so it is written differently from the defects. A
feature request competes with every other feature request; what makes this one
worth reading is that it arrives with the implementation constraint already
found, so it leads on that rather than on the want. Filing it as `wishlist`
severity matters — a feature request filed as a bug gets reclassified and reads
as though the reporter did not know the difference.

The cross-reference to #6 now carries its real number, 524246 — ready to paste
as-is.

### Report body to paste

```text
SUMMARY

There is no setting anywhere in Plasma for the opacity of a desktop widget's
background frame.

Desktop widgets always take the StandardBackground path in
BasicAppletContainer.qml:

    if (effectiveBackgroundHints & TranslucentBackground) return "widgets/translucentbackground";
    else if (effectiveBackgroundHints & StandardBackground) return "widgets/background";

so the frame is whatever widgets/background.svgz draws, at full opacity.

WHAT I AM ASKING FOR

A per-widget or theme-level opacity control for the applet background frame.

AN IMPLEMENTATION CONSTRAINT WORTH KNOWING UP FRONT

The obvious implementation -- render the frame as usual, then wrap it in a single
opacity group -- does not work. Ancestor opacity is not applied when Qt renders
an SVG by element id, and rendering by element id is how KSvg draws frame parts.

The only approach I found that does work is setting an opacity attribute on each
of the nine <g> elements individually: center, top, bottom, left, right, and the
four corners. The shadow-* elements are best left opaque, or panels stop reading
against a busy wallpaper.

I mention it because it rules out the cheapest version of this feature, and it
took a while to establish.

WORKAROUND, FOR ANYONE WHO LANDS HERE

Shadow the theme into ~/.local/share/plasma/desktoptheme/ and patch those nine
elements in widgets/background.svgz by hand. The cost is real rather than
cosmetic: while the shadow copy exists, distro updates to that theme stop
reaching you.

Note also that translucent/widgets/background.svgz, shipped by every theme, is
the obvious first thing to patch and appears to be referenced by nothing, so
patching it has no effect. Reported separately as bug 524246.

Operating System: Ubuntu 26.04 LTS (Kubuntu)
KDE Plasma Version: 6.6.6
KDE Frameworks Version: 6.24.0
Qt Version: 6.10.2
Graphics Platform: Wayland
```
