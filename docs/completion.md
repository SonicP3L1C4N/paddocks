<!--
SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>

SPDX-License-Identifier: MIT
-->

# What "finished" means for Paddocks

Written 2026-08-21, a week after the upstream reports went in. Paddocks has no
release, no version number anyone could ask for, and no definition of done — so
it can absorb work indefinitely. This file is the stopping condition.

Three tracks. They finish at different times and only one of them is v1.0.

---

## Track A — the upstream record

The reports were always the point; the tool is the evidence that produced them
(see `plasma-bugs.md`). This track is done when every report has a terminal state
and nothing in this repo claims something Bugzilla contradicts.

| Item | Done when |
|---|---|
| **524247** (NEEDSINFO, wishlist) | ~~Nate's "what's the use case?" is answered.~~ **Done 2026-08-21** — answered as comment #2, and the status moved off NEEDSINFO by hand (a comment does not do it) to UNCONFIRMED. Nothing further owed; it waits on triage now. |
| **524246** (CONFIRMED, MR invited) | ~~The selector experiment has been run.~~ **Run 2026-08-21: the report is wrong**, the assets are live. ~~Done when the retraction is posted and the bug resolved INVALID.~~ **Done** — comment #3, RESOLVED/INVALID, 2026-08-21. No MR. |
| **524245** (UNCONFIRMED, ignored) | ~~One follow-up comment with a cleaner reproduction.~~ **Done 2026-08-21** — tested three ways including a backdated mtime, retracted as comment #1, RESOLVED/INVALID. Two of the seven reports retracted by their own reporter is not a good look, but posting neither would be worse. |
| **524242** (FIXED) | README finding 1 says it is fixed in KIO master and absent from 6.24 LTS, and the workaround stays for LTS users. |
| **524243, 524244** (WONTFIX) | README findings 1 and 3 are rewritten to describe deliberate trade-offs rather than defects, quoting the reasoning. No re-litigation. |
| **362511** (CONFIRMED, 2016) | Nothing. Comment #5 stands. |
| **524520** (new, UNCONFIRMED) | ~~File the `evaluateScript` report.~~ **Filed 2026-08-21.** Nothing further owed; it waits on triage. |

**Track A is complete as of 2026-08-21.** Every report has a terminal state or is
sitting with a triager, and nothing in this repo contradicts Bugzilla. Two of the
original seven were retracted by their own reporter, one was already fixed
upstream, two were answered as intentional, one wishlist is open and answered,
and one new report came out of the work. What is left is watching, which is not a
task.

The honest failure mode for this track is arguing with WONTFIX. Two of five
findings turned out to be intentional behaviour; saying so plainly in the README
is worth more than the original claim was.

## Track B — Paddocks 1.0

The tool is done when someone other than its author can install it, use it, and
hit only documented limits.

* [x] **Multi-monitor is resolved.** *Done 2026-08-21* — **handled, not
      refused.** A second monitor arrived the same afternoon, which made the
      refusal lock Gary out of his own tool and made the real thing testable for
      the first time. `screen = N` per group, `paddocks screens` to find the
      index, one layout solved per screen against its own size, widgets created
      on that screen's containment and positions written under its own
      `ItemGeometries-<W>x<H>` key. Verified live on 3440x1440 + 2560x1440:
      applied a split config, confirmed both geometry keys and the placement,
      then restored the original layout.
* [x] **CI.** *Done 2026-08-21* — `.github/workflows/ci.yml` runs the suite on
      3.11/3.12/3.13, again with the editor extra under `QT_QPA_PLATFORM=offscreen`,
      and `reuse lint`. Nothing had been enforcing the 152 tests.
* [x] **`remove` reaches other screens.** *Done 2026-08-21* — it swept only
      `desktops()[0]`, so a widget on a second monitor was reported removed
      without being removed. Verified: containment 247 had no applets left after
      the restore.
* [ ] **The translucency fix needs a real-desktop run.** `apply` now patches
      `translucent/widgets/background.svgz` as well; that path is covered by
      unit tests against a fake theme tree but has not been run against the
      live desktop since the change.
* [ ] **A tagged 1.0.0**, installable with `pipx install`, with a CHANGELOG.
      Currently `0.1.0` in `paddocks/__init__.py`.
* [ ] **README matches upstream reality** — the Track A doc edits.
* [ ] **One clean install on a machine that is not this one**, or the
      "tested on one machine" caveat is promoted from a footnote to the top of
      the README. Two screens on one machine is not two machines.

Explicitly *not* in 1.0: mixed launcher/folder groups, theming beyond the
existing `translucency` command, X11 support, anything that needs Plasma to
change first.

## Track C — KDE

Out of scope for 1.0 and gated on things that are not Gary's to decide: a second
contributor, and someone inside KDE interested enough to sponsor. The entry
ticket is a *merged* contribution. 524246 looked like that ticket — it was the
only one of the seven that came with an invitation — and the experiment on
2026-08-21 turned it into a retraction instead. Declining to submit an MR you
have disproved is worth more here than the MR would have been, but it does mean
Track C has no open door at the moment and the next one has to be found.

Track C is not "done" or "not done". It is either open or it is closed, and it
stays open as long as the bug work continues.
