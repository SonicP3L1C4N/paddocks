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

**All seven were upstream on 2026-08-14** — six new reports, 524242 to 524247,
plus a comment on the ten-year-old 362511. **Six of the seven had a reply within
a day**, all from Nate Graham; the outcomes as of 2026-08-21 are below.

Products and components below were checked against Bugzilla on 2026-08-14 and are
exact. Note there is **no `plasma-workspace` product** — the Plasma shell,
including the code that ships in the `plasma-workspace` package, is filed under
`plasmashell`.

| # | Bug | Status on 2026-08-21 | Outcome |
|---|---|---|---|
| 1 | [524242](https://bugs.kde.org/show_bug.cgi?id=524242) `desktop:/ IOWorker` | **RESOLVED FIXED** | Already fixed upstream in KIO ([4901a6cc](https://invent.kde.org/frameworks/kio/-/commit/4901a6cc7129dcfc2fae23c8526db31dd811b486)); not backported to the 6.24 LTS branch because the fix needed a substantive UI change. |
| 2 | [524243](https://bugs.kde.org/show_bug.cgi?id=524243) `Folder View widget` | **RESOLVED WONTFIX** | Intentional both ways: `file://` withholds `Name=` on purpose, and `desktop:/` exists partly *to* show it. Accepted trade-off, not an oversight. |
| 3 | [362511](https://bugs.kde.org/show_bug.cgi?id=362511) `Scripting` | CONFIRMED, no reply | Comment #5 stands. Nothing to do but watch. |
| 4 | [524244](https://bugs.kde.org/show_bug.cgi?id=524244) `general` | **RESOLVED WONTFIX** | "Works for me": the tool did apply the theme and exiting 0 is correct; the later reset is the automatic switcher doing its job. The report's actual complaint — that `plasmarc` is left disagreeing with the screen with no warning — was not addressed. |
| 5 | [524245](https://bugs.kde.org/show_bug.cgi?id=524245) frameworks-ksvg | UNCONFIRMED, no reply | Nobody looked at it, and on 2026-08-21 **it turned out to be wrong too** — see below. Needs retracting. |
| 6 | [524246](https://bugs.kde.org/show_bug.cgi?id=524246) `Theme - Breeze` | **RESOLVED / INVALID** 2026-08-21 | Was CONFIRMED, with an invitation to submit a removal MR. Tested instead; the premise was wrong. Retracted by the reporter as comment #3 and closed. |
| 7 | [524247](https://bugs.kde.org/show_bug.cgi?id=524247) `Containment` | NEEDSINFO, **answered 2026-08-21** | "Why? What's the use case for this?" — answered as comment #2 with the narrowed ask. Status still needs setting back to REPORTED by hand. |

### The 524246 problem, found 2026-08-21

524246 says `translucent/widgets/background.svgz` "is shipped by every theme and
referenced by nothing", and it is CONFIRMED with an invitation to delete it.
Reading the source says otherwise, and an MR that deletes a live asset is the
worst possible first contribution.

The mechanism is KSvg *selectors*:

* `ThemePrivate::updateKSvgSelectors()` (libplasma `src/plasma/private/theme_p.cpp`,
  v6.6.6) sets `kSvgImageSet->setSelectors({"translucent"})` whenever compositing
  is on **and** the blur effect is active, and `{"opaque"}` when compositing is off.
* `ImageSetPrivate::findInImageSet()` (ksvg `src/ksvg/private/imageset_p.cpp`)
  tries `<theme>/<selector>/<image>` for each selector *before* `<theme>/<image>`,
  and repeats the whole search across the fallback themes.
* On 6.6.6 "blur is active" means the Wayland `org_kde_kwin_blur_manager` global
  is bound. `wayland-info` on this machine lists it, so the selector should be on.

So `translucent/` is not dead code — it is a whole second variant of the theme,
selected automatically. `opaque/` is the same mechanism for the non-composited
case. Neither is referenced by name anywhere, which is exactly why grepping for
them finds nothing and why the report reads as convincing.

What is still unexplained is the original observation: patching that file changed
nothing on screen. Candidates, in order of likelihood:

1. The patched file was in a theme that was not on the resolved search path —
   the active theme is `kubuntu-light` (shadowed in `~/.local/share`), which ships
   no `translucent/` directory of its own.
2. The blur global is advertised but `BlurManager::isActive()` is false at the
   moment `updateKSvgSelectors()` runs, so the selector is never set.
3. The selector is set and the asset genuinely is not used for *desktop applet*
   frames specifically.

(1) means 524246 must be retracted. (3) would be a better bug than the one filed.
**This has to be settled by experiment before anything is submitted or posted.**

### The experiment, run 2026-08-21 — the report is wrong

A magenta, fully opaque `background.svgz` was placed at
`~/.local/share/plasma/desktoptheme/kubuntu-light/translucent/widgets/`, the
theme caches were cleared with plasmashell stopped, and the shell restarted.
**Every desktop widget frame turned magenta.** The selector path is live on
6.6.6, and it takes precedence over `kubuntu-light/widgets/background.svgz`,
which is the file the `translucency` command patches.

The original negative result is explained by hypothesis (1): the active theme is
`kubuntu-light`, which shadows only `widgets/background.svgz` and ships no
`translucent/` directory. `findInImageSet()` tries the selector path *and* the
plain path within the current theme before moving on to the fallback theme, so
`kubuntu-light/widgets/background.svgz` wins and Breeze's
`translucent/widgets/background.svgz` is never reached. The file that was patched
was never on the resolved path.

Comparing the two stock Breeze assets confirms the intent — `translucent/` is not
a copy, it is a different drawing:

| | `widgets/background.svgz` | `translucent/widgets/background.svgz` |
|---|---|---|
| size | 30619 bytes | 48662 bytes |
| frame opacities | `0.875` | `0.8` and `0.2` |
| extra elements | — | nine `blurred-mask-*`, one per frame part |

The `blurred-mask-*` elements are how the widget tells KWin what region to blur
behind it. So a theme that overrides only `widgets/background.svgz` — which is
what `paddocks translucency` does, and what Kubuntu's own theme does — silently
opts every widget out of Plasma's blur-aware background. Nothing reports it.

**524246 must be retracted, not merged into an MR.** Draft below.

---

## Outstanding replies, drafted 2026-08-21

Plain text, because Bugzilla does not render markdown.

### For 524246 — retraction — **POSTED 2026-08-21**

Posted as comment #3 and resolved **RESOLVED / INVALID**. Gary trimmed it on the
way in; the draft below is what was written, not verbatim what is on the bug.

One paragraph was cut, and it is the only part that pointed forward rather than
backward — that the two Breeze assets are not copies of each other, and that a
theme overriding only `widgets/background.svgz` therefore drops the nine
`blurred-mask-*` elements and silently opts its widgets out of the blur. That
observation is now recorded **nowhere upstream**. Fair enough on a bug being
closed INVALID, where nobody is likely to read it. If it is worth raising, it
wants its own report against the Breeze theme or a note on the discuss thread —
not a comment on a dead bug.

```text
I need to retract this, and I am glad I tested before opening the merge request:
removing those files would have been a regression.

translucent/ is not unreferenced. It is reached through KSvg selectors, and the
path is never written down anywhere, which is why grepping for it finds nothing.

ThemePrivate::updateKSvgSelectors() in libplasma (src/plasma/private/theme_p.cpp,
v6.6.6) calls kSvgImageSet->setSelectors({"translucent"}) whenever compositing is
active and the blur effect is available, and {"opaque"} when compositing is off.
ImageSetPrivate::findInImageSet() in ksvg (src/ksvg/private/imageset_p.cpp) then
tries <theme>/<selector>/<image> ahead of <theme>/<image>, repeating the whole
search across the fallback themes.

Tested rather than argued from the source: I put an obviously wrong background
(flat magenta, fully opaque) at

    ~/.local/share/plasma/desktoptheme/kubuntu-light/translucent/widgets/background.svgz

stopped plasmashell, cleared ~/.cache/plasma_theme_*.kcache and
~/.cache/ksvg-elements, and started it again. Every desktop widget frame picked
it up. The selector is live on 6.6.6 under Wayland with KWin advertising
org_kde_kwin_blur_manager.

Why my original test showed nothing: my active theme is kubuntu-light, which
shadows only widgets/background.svgz and ships no translucent/ directory of its
own. findInImageSet() tries the selector path and then the plain path within the
current theme before falling through to Breeze, so kubuntu-light's plain file
wins and Breeze's translucent variant is never consulted. I patched a file that
was not on the resolved path and concluded the file was dead.

One observation that may be worth someone's time, though it is not what I
reported: the two Breeze assets are not copies of each other. The translucent
variant is less opaque and carries nine blurred-mask-* elements, one per frame
part, which is how the widget tells KWin what to blur behind it. A theme that
overrides only widgets/background.svgz therefore opts all of its widgets out of
the blur-aware background silently -- no warning to the theme author, and no
visible symptom beyond "blur does not seem to work with this theme". That is
arguably correct precedence, since an explicit override should win. It is just
invisible when it goes wrong.

Sorry for the noise on this one.
```

Resolved INVALID by the reporter at the same time, which is right: leaving a
CONFIRMED bug standing on a premise its own reporter has disproved is worse than
having filed it.

### For 524247 — answering "what's the use case?" — **POSTED 2026-08-21**

Posted as comment #2, trimmed. **The bug was still NEEDSINFO / WAITINGFORINFO
afterwards** — a comment does not clear that state on KDE Bugzilla, the status
has to be set back to REPORTED by hand.

What was trimmed loses nothing: the nine-`<g>` implementation constraint and the
"ancestor opacity is not applied when rendering by element id" finding are
already in comment #0, which is the report body. Restating them would have been
noise. The closing paragraph offering to accept "go and make a theme" also went,
which reads more confidently without it.

```text
Yes. Concretely: grouped launcher panels on the desktop.

I build titled boxes of launchers directly on the desktop -- a Quicklaunch widget
per group, positioned and sized like a small panel. Six of them cover a good
fraction of a 3440x1440 screen. At the standard applet background opacity the
desktop stops being a desktop and becomes a slab of frames: the wallpaper is the
only reason those widgets are on the desktop rather than in a panel, and the
frames are what hides it.

What I want is one number per widget -- the opacity of its background frame --
so a group can sit over the wallpaper the way a panel sits over a window.

Since filing this I found I had the mechanism wrong, and the request is narrower
than I wrote it. Plasma already varies the applet background by blur
availability: updateKSvgSelectors() sets the "translucent" KSvg selector when
blur is active, and Breeze's translucent/widgets/background.svgz is a genuinely
different asset -- lower opacities, plus nine blurred-mask-* elements. So the
rendering path exists and is live. What is missing is anything that exposes it,
and any way to land between or beyond the two variants a theme happens to ship.

So the ask is: a per-widget background opacity setting in the widget's own
settings dialog, defaulting to whatever the theme currently gives.

The implementation constraint from the original report still holds for anyone
picking this up: wrapping the frame in a single opacity group does not work,
because ancestor opacity is not applied when Qt renders an SVG by element id, and
rendering by element id is how KSvg draws frame parts. Setting an opacity
attribute on each of the nine <g> elements individually does work -- leaving the
shadow-* elements opaque, or frames stop reading against a busy wallpaper.

If the answer is "this belongs in a theme, go and make a theme", that is a fair
answer and I will take it. It is worth knowing what it costs the user today,
though: it means shadowing a system theme into ~/.local/share under its own name,
after which distro updates to that theme stop reaching them, and -- per the
paragraph above -- silently drops the blurred-mask-* elements unless they think
to copy the translucent variant too.
```

### For 524245 — retraction

**Tested 2026-08-21, and it does not reproduce.** The report claims the theme
pixmap cache is keyed by name only, with "no mtime or content check", so an
in-place edit is served stale indefinitely. Three variants against the active
theme, patching `widgets/background.svgz` in place with an unmistakable colour
and never clearing a cache:

| What was changed | Result |
|---|---|
| artwork changed while plasmashell was running | picked up within seconds, no restart needed |
| artwork changed while plasmashell was stopped, then started | picked up |
| same, with the file's mtime backdated well below the cache file's | still picked up |

The first run of this was botched and worth recording: the file was patched
while the shell was still up, so the shell noticed it live and refreshed the
caches four seconds later — the subsequent restart then loaded caches that were
already current, which proves nothing about staleness. The change has to be made
while plasmashell is down for the test to mean anything.

The source agrees. `SvgRectsCache` records a per-file `LastModified` in
`~/.cache/ksvg-elements` and rejects a cached entry whose file mtime differs
(`svg.cpp`, `loadImageFromCache` / `lastModifiedTimeFromCache`). The comparison
is `!=`, which is why the backdated case is caught too.

So the original observation — patching a theme asset and seeing nothing change —
was real, and the cause was not the cache. It was the same mistake as 524246:
patching a file that was not on the resolved path.

**This also means the README was wrong about clearing the cache being required**,
and it is fixed there. Paddocks still clears it, on one narrow ground: these
mtimes have one-second resolution and `apply` writes a theme file and restarts
the shell immediately, so two edits inside the same second are conceivable. That
is insurance, not a workaround.

```text
Retracting this: I cannot reproduce it on 6.6.6, and I now think the report was
wrong when I filed it.

Three variants, all against the active theme (kubuntu-light, shadowed into
~/.local/share under its own name), patching widgets/background.svgz in place
with an unmistakable colour, never clearing any cache:

1. Changed while plasmashell was running -- picked up within seconds, without a
   restart.
2. Changed while plasmashell was stopped, then started -- picked up.
3. Changed while stopped, with the file's mtime backdated to well before the
   cache file's, then started -- still picked up.

The caches do track this. SvgRectsCache records a per-file LastModified in
~/.cache/ksvg-elements and rejects a cached entry whose file mtime differs
(svg.cpp, loadImageFromCache and lastModifiedTimeFromCache). The comparison is
!=, so a timestamp moving backwards is caught as well as one moving forwards.

For anyone repeating this: the change has to be made while plasmashell is
stopped. My first attempt patched the file with the shell running, which noticed
it live and refreshed the caches on its own, so the restart afterwards proved
nothing.

What I originally saw -- patching a theme asset and nothing changing -- was real,
but the cause was not the cache. I was patching a file that was not on the
resolved path: KSvg resolves <theme>/<selector>/<image> ahead of <theme>/<image>
when the "translucent" selector is set, and my active theme shadowed only the
plain asset. That is also what was wrong with bug 524246, which I have retracted
as well.

Sorry for the noise. Please close.
```

### New report — `evaluateScript` runs `print()` output together

**Not yet filed.** Found 2026-08-21 while enumerating screens for multi-monitor
support; it is what made the first version of that code fail.

**Product:** plasmashell · **Component:** `Scripting` · **Severity:** normal ·
**Version:** 6.6.6

Not a duplicate: the component holds nine bugs, none about script output —
362511 (geometry, ours), 433799, 512005, 513669, 515385, 515789, 518887, 521549,
523675.

Severity `normal` rather than `minor` on the same reasoning as report 5: this is
wrong output rather than a cosmetic nit, and it corrupts the caller's data
quietly instead of failing.

```text
SUMMARY

The string returned by org.kde.PlasmaShell.evaluateScript joins the output of
successive print() calls with no separator. A script that prints more than one
value comes back as a single run-together string, and there is nothing in it to
say where one value ends and the next begins.

STEPS TO REPRODUCE

    qdbus6 org.kde.plasmashell /PlasmaShell \
        org.kde.PlasmaShell.evaluateScript 'print("one"); print("two");'

OBSERVED RESULT

    onetwo

EXPECTED RESULT

    one
    two

print() terminating a record is what the name implies, and what the equivalent
in every other scripting console does.

ADDITIONAL INFORMATION

The transport is not the problem -- a newline inside a single print() survives
the round trip:

    ... evaluateScript 'print("one\ntwo");'
    one
    two

so it is print() that does not append one.

Why it is worth fixing rather than working around: the failure produces
plausible output rather than obviously broken output. Enumerating screens --

    for (var i = 0; i < screenCount; i++) {
        var g = screenGeometry(i);
        print(i + " " + g.width + "x" + g.height);
    }

returns

    0 3440x14401 2560x1440

on a two-screen desktop. The "1" that opens the second record is glued to the
first record's height, so the first screen reads as 14401 pixels tall and the
second record is missing its index. Every field still looks like a number.
Splitting the result on newlines -- the obvious thing to do, and correct for
single-record scripts -- yields one record containing all of them.

The workaround is for the script to emit its own separator, which is fine once
you know. Until you know, it looks like the Plasma API is returning bad values.

Operating System: Ubuntu 26.04 LTS (Kubuntu)
KDE Plasma Version: 6.6.6
KDE Frameworks Version: 6.24.0
Qt Version: 6.10.2
Graphics Platform: Wayland
```

---


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
content. Comment 0 is not editable by the reporter on KDE Bugzilla, so it was
retracted in the follow-up below — **posted as comment #1 at 03:57 UTC**, four
minutes after the report.

Net effect: the bug now carries the full cache-clearing step and the version
block, neither of which was in the description, so it reads better than a clean
filing of the original draft would have. The paste block further down is the
corrected body, kept for the record; it was never posted as such.

### Follow-up comment, posted as comment #1

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

**Filed 2026-08-14 as [bug 524247](https://bugs.kde.org/show_bug.cgi?id=524247)**
— status REPORTED, severity wishlist, version 6.6.6, cross-reference to 524246
intact.

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
