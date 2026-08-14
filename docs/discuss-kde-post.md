<!--
SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>

SPDX-License-Identifier: MIT
-->

# discuss.kde.org post — draft

Companion to [plasma-bugs.md](plasma-bugs.md), which is the record of the six
reports this post points at.

**Posted 2026-08-14:**
https://discuss.kde.org/t/grouped-desktop-launcher-panels-on-plasma-6-and-five-things-that-fail-silently/49388

The account was auto-held first — Discourse caps trust-level-0 users at two links
per post and this one had eight, all but one of them to KDE's own Bugzilla. A
moderator approved it.

**Defect in post #1, corrected in post #2:** it went up without backticks around
`ItemGeometries-<W>x<H>`, so Discourse stripped `<W>` and `<H>` as unknown HTML
tags and the line renders as `ItemGeometries-x`. Editing was not an option — at
trust level 0 the post carries link, bookmark, delete and reply, but no pencil —
so a follow-up reply carries the corrected token instead. That reply is
deliberately link-free: TL0 is what got the account held in the first place, and
seven Bugzilla links in a reply would risk tripping the same filter.

The bug numbers in post #1 are plain text rather than links, for the same reason.
Worth adding once the account reaches TL1 and editing unlocks.

**Lesson for any future Discourse post:** anything shaped like an HTML tag needs
backticks, and the composer preview will not show you the problem.

**Category:** Development (add a `plasma` tag). Not Help — this is not a support
request, and posting it there would get it answered rather than discussed.

**Title:** Grouped desktop launcher panels on Plasma 6, and five things that fail silently

Discourse renders markdown, so the formatting below is intended — paste as-is.

Two things that must survive the paste: the bug numbers are markdown links
(Discourse will not auto-link a bare Bugzilla id), and `ItemGeometries-<W>x<H>`
is backticked because Discourse strips unrecognised HTML tags — unbackticked,
`<W>` and `<H>` disappear and the line renders as `ItemGeometries-x`.

---

I've spent the last few days building a small tool that groups desktop launchers
into titled panels in Plasma 6 — the kind of thing desktop organiser tools do on
Windows. It's called Paddocks: a TOML file describes the groups, and it builds
them out of stock Quicklaunch widgets. https://github.com/SonicP3L1C4N/paddocks

I'm not posting to advertise it. Plasma could already do nearly all of this — the
problem is that the route there is undocumented, and several steps along the way
fail silently. I've filed what I found, and there's a design question at the end
that I'd value opinions on.

## What I filed

- **[524242](https://bugs.kde.org/show_bug.cgi?id=524242)** — `desktop:/` subpaths
  list correctly, but launching a `.desktop` file through one exits 0 and starts
  nothing. A Folder View pointed at `desktop:/Apps` renders a perfect grid of
  inert icons.
- **[524243](https://bugs.kde.org/show_bug.cgi?id=524243)** — Folder View at a
  `file://` URL labels `.desktop` files by filename rather than `Name=`, while
  `desktop:/` labels the same files correctly.
- **[524244](https://bugs.kde.org/show_bug.cgi?id=524244)** —
  `plasma-apply-desktoptheme` reports success and writes `plasmarc` while
  `AutomaticLookAndFeel` silently overrides the result.
- **[524245](https://bugs.kde.org/show_bug.cgi?id=524245)** — the theme pixmap
  cache is keyed by theme name only, so editing a theme in place never
  invalidates it.
- **[524246](https://bugs.kde.org/show_bug.cgi?id=524246)** —
  `translucent/widgets/background.svgz` ships in every theme and appears to be
  referenced by nothing.
- **[524247](https://bugs.kde.org/show_bug.cgi?id=524247)** — wishlist: no way to
  set the opacity of a widget's background frame.

I also added a comment to **[362511](https://bugs.kde.org/show_bug.cgi?id=362511)**
(setting widget geometry from the scripting API, open since 2016) describing the
failure mode: `Qt` is undefined, so `Qt.rect()` throws, assigning a plain object
is silently discarded, and reading the property back returns the auto-placed
position — so it looks as though Plasma accepted the value and then re-laid out
over the top of it.

## The design question

That last one is why I'm posting rather than only filing. Because widget geometry
can't be set from scripting, the only way to place a widget is to stop
plasmashell, write `ItemGeometries-<W>x<H>` to
`plasma-org.kde.plasma.desktop-appletsrc`, and start plasmashell again. That's a
private format behind a shell restart. Anything built in this space is fragile by
construction — a point release can change the format and break every tool relying
on it.

So the question is: **does Plasma want grouped desktop organisation natively?**
And if it does, what's the right shape — a containment feature, a widget, or
simply making the layout scripting API able to place things, so external tools
stop needing the back door?

I'd genuinely rather this tool became unnecessary than adopted. If the answer is
"that belongs in the containment", that's a better outcome than me maintaining a
workaround indefinitely.

## Caveats, so nobody wastes time

Tested on exactly one machine: Plasma 6.6.6, Kubuntu 26.04, Wayland, a single
3440×1440 screen. Multi-monitor is unhandled. It's Python and uses no KDE
Frameworks — it talks to Plasma over D-Bus and config files.

I used Claude Code throughout this: working out Plasma's config internals,
chasing down the failure modes above, and writing Paddocks itself. Everything in
those reports is behaviour I reproduced on the machine described above — the
commands in them are commands I ran, and the observed results are what I saw.
Where I wasn't certain, the report says so rather than asserting; 524243 states
outright that it may be intentional and should be closed as NOTABUG if so.
Flagging it because I'd rather be up front than have anyone wonder.

Happy to test patches on any of the above; I have a setup that reproduces all of
it.
