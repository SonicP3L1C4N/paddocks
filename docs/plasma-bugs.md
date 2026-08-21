<!--
SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>

SPDX-License-Identifier: MIT
-->

# Upstream reports

The README's five findings, as filed at [bugs.kde.org](https://bugs.kde.org),
with what became of each. Filed 2026-08-14; outcomes as of 2026-08-21.

| Bug | Product / component | Outcome |
|---|---|---|
| [524242](https://bugs.kde.org/show_bug.cgi?id=524242) | plasmashell / `desktop:/ IOWorker` | **FIXED** — already fixed in KIO by [4901a6cc](https://invent.kde.org/frameworks/kio/-/commit/4901a6cc7129dcfc2fae23c8526db31dd811b486), not backported to the 6.24 LTS branch |
| [524243](https://bugs.kde.org/show_bug.cgi?id=524243) | plasmashell / `Folder View widget` | **WONTFIX** — intentional; `desktop:/` exists partly *to* show `Name=`, and the inconsistency is an accepted trade-off |
| [524244](https://bugs.kde.org/show_bug.cgi?id=524244) | plasmashell / `general` | **WONTFIX** — the tool did apply the theme, so exit 0 is correct; the later reset is the automatic switcher working |
| [524245](https://bugs.kde.org/show_bug.cgi?id=524245) | frameworks-ksvg / `General` | **INVALID** — retracted, see below |
| [524246](https://bugs.kde.org/show_bug.cgi?id=524246) | plasmashell / `Theme - Breeze` | **INVALID** — retracted, see below |
| [524247](https://bugs.kde.org/show_bug.cgi?id=524247) | plasmashell / `Containment` | open — wishlist, use case supplied |
| [524520](https://bugs.kde.org/show_bug.cgi?id=524520) | plasmashell / `Scripting` | open — `evaluateScript` runs `print()` output together; found while writing multi-monitor support |
| [362511](https://bugs.kde.org/show_bug.cgi?id=362511) | plasmashell / `Scripting` | open since 2016 — commented rather than filed fresh; widget geometry is not settable from the scripting API |

## The two that were wrong

524245 and 524246 were retracted by their own reporter after being tested
properly, and both failed the same way.

**524246** claimed `translucent/widgets/background.svgz` was shipped by every
theme and referenced by nothing. It is referenced — by KSvg *selectors*, which
never write the path down anywhere, which is why grepping for it finds nothing.
`ThemePrivate::updateKSvgSelectors()` sets the `translucent` selector whenever
compositing and blur are both active, and `findInImageSet()` then resolves
`<theme>/<selector>/<image>` ahead of `<theme>/<image>`, finishing the current
theme before falling through to the fallback theme. The bug was CONFIRMED, with
an invitation to submit a merge request deleting the files. Testing first is the
only reason that merge request was never opened.

**524245** claimed the theme pixmap cache is keyed by name with no mtime or
content check, so an edit under the same name is served stale forever. KSvg
records a per-file `LastModified` in `~/.cache/ksvg-elements` and rejects an
entry whose file mtime differs — and the comparison is `!=`, so backdating the
file does not fool it either.

Both had the same root cause: a file was patched that was not on KSvg's resolved
path, and "nothing changed" was read as "nothing reads this file". Finding 5 in
the README documents what actually happens.

One trap worth repeating, because the first attempt at re-testing 524245 fell
into it: the change has to be made **while plasmashell is stopped**. A running
shell notices the edit itself and refreshes the caches, so a restart afterwards
proves nothing and looks exactly like a passing test.
