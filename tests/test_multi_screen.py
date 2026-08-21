# SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Placing groups on more than one screen.

Three things have to line up, and none of them announces itself when it does
not. Each screen is laid out against *its own* size; each group is created on
the containment belonging to its screen, which is not the same number as the
screen index; and each containment's positions are written under a key naming
that screen's resolution, because a key naming another screen's size is simply
not read.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from paddocks import apps, groups, plasma
from paddocks.layout import Metrics

from .support import FakePlasma

TWO = [(1920, 1080), (1280, 1024)]


class ReadingTheScreens(unittest.TestCase):
    """`screens()` against a faked evaluateScript."""

    def screens_for(self, output):
        with mock.patch.object(plasma, "run_script", return_value=output):
            return plasma.screens()

    def test_reads_one_record_per_screen(self):
        found = self.screens_for("0 1920 1080 1\x1e1 1280 1024 247\x1e")
        self.assertEqual([(s.index, s.width, s.height, s.containment)
                          for s in found],
                         [(0, 1920, 1080, 1), (1, 1280, 1024, 247)])

    def test_records_are_split_on_the_separator_not_on_newlines(self):
        """print() does not append one, so the records arrive glued together."""
        found = self.screens_for("0 1920 1080 1\x1e1 1280 1024 247\x1e")
        self.assertEqual(len(found), 2)

    def test_resolution_is_the_itemgeometries_key_suffix(self):
        found = self.screens_for("0 3440 1440 1\x1e")
        self.assertEqual(found[0].resolution, "3440x1440")

    def test_no_screens_is_an_error(self):
        with self.assertRaises(plasma.PlasmaError):
            self.screens_for("")

    def test_a_screen_with_no_containment_is_an_error(self):
        """-1 means no containment on the current activity; nothing can go there."""
        with self.assertRaises(plasma.PlasmaError) as caught:
            self.screens_for("0 1920 1080 1\x1e1 1280 1024 -1\x1e")
        self.assertIn("no desktop containment", str(caught.exception))

    def test_garbled_output_is_an_error_rather_than_a_guess(self):
        with self.assertRaises(plasma.PlasmaError):
            self.screens_for("0 1920 1080\x1e")


class TheConfigKey(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paddocks.toml"
            path.write_text(text)
            return groups.load_config(path)

    def test_defaults_to_screen_zero(self):
        cfg = self.load('[[group]]\nname = "G"\napps = ["a"]\n')
        self.assertEqual(cfg.groups[0].screen, 0)

    def test_reads_a_screen_index(self):
        cfg = self.load('[[group]]\nname = "G"\napps = ["a"]\nscreen = 1\n')
        self.assertEqual(cfg.groups[0].screen, 1)

    def test_rejects_a_negative_index(self):
        with self.assertRaises(groups.ConfigError) as caught:
            self.load('[[group]]\nname = "G"\napps = ["a"]\nscreen = -1\n')
        self.assertIn("0 or more", str(caught.exception))

    def test_rejects_a_non_integer(self):
        with self.assertRaises(groups.ConfigError):
            self.load('[[group]]\nname = "G"\napps = ["a"]\nscreen = "left"\n')

    def test_it_survives_a_round_trip_through_the_writer(self):
        cfg = self.load('[[group]]\nname = "G"\napps = ["a"]\nscreen = 2\n')
        self.assertIn("screen = 2", groups.dump_config(cfg))

    def test_screen_zero_is_not_written_out(self):
        """The default is what every single-monitor config already means."""
        cfg = self.load('[[group]]\nname = "G"\napps = ["a"]\n')
        self.assertNotIn("screen =", groups.dump_config(cfg))


class Placing(unittest.TestCase):
    def _apply(self, group_screens, screens=TWO):
        printed: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            config = groups.Config(
                groups=[groups.Group(f"G{i}", ["nothing"], screen=s)
                        for i, s in enumerate(group_screens)],
                metrics=Metrics())
            fake = FakePlasma(state, screens=screens)
            fake.state_json = {}
            with mock.patch.object(groups, "plasma", fake), \
                 mock.patch.object(groups, "STATE_FILE", state / "state.json"), \
                 mock.patch.object(groups.apps, "build",
                                   return_value=apps.Index()), \
                 mock.patch("builtins.print",
                            side_effect=lambda *a, **k: printed.append(" ".join(map(str, a)))):
                error = None
                try:
                    groups.apply(config)
                except ValueError as exc:
                    error = str(exc)
            # Read while the temporary directory still exists.
            written = state / "state.json"
            if written.exists():
                import json
                fake.state_json = json.loads(written.read_text())
            return error, printed, fake

    def test_each_group_is_built_on_its_own_screens_containment(self):
        _, _, fake = self._apply([0, 1, 0])
        # Containment 1 is screen 0 and containment 2 is screen 1.
        self.assertEqual([containment for containment, _ in fake.built], [1, 2])
        self.assertEqual([[spec["title"] for spec in specs]
                          for _, specs in fake.built],
                         [["G0", "G2"], ["G1"]])

    def test_geometry_is_written_per_containment_with_that_screens_key(self):
        _, _, fake = self._apply([0, 1])
        self.assertEqual([(c, r) for c, r, _ in fake.geometries],
                         [(1, "1920x1080"), (2, "1280x1024")])

    def test_a_screen_with_no_groups_is_skipped_entirely(self):
        _, _, fake = self._apply([0, 0])
        self.assertEqual([containment for containment, _ in fake.built], [1])
        self.assertEqual(len(fake.geometries), 1)

    def test_every_widget_lands_in_state_whichever_screen_it_is_on(self):
        """`remove` works off state, so a widget missing from it is unreachable."""
        _, _, fake = self._apply([0, 1, 1])
        recorded = fake.state_json
        self.assertEqual([w["name"] for w in recorded["widgets"]],
                         ["G0", "G1", "G2"])
        self.assertEqual(len({w["id"] for w in recorded["widgets"]}), 3)

    def test_state_records_where_each_screen_was_written(self):
        _, _, fake = self._apply([0, 1])
        recorded = fake.state_json
        self.assertEqual(recorded["screens"],
                         [{"screen": 0, "containment": 1, "resolution": "1920x1080"},
                          {"screen": 1, "containment": 2, "resolution": "1280x1024"}])

    def test_a_group_on_a_screen_that_is_not_there_is_refused(self):
        error, _, fake = self._apply([0, 3])
        self.assertIn("screen [3]", error)
        self.assertIn("1920x1080", error)
        self.assertEqual(fake.built, [], "nothing may be created before the check")

    def test_the_layout_uses_each_screens_own_width(self):
        """A box laid out for the wide screen would overhang the narrow one."""
        _, printed, _ = self._apply([1] * 6, screens=[(1920, 1080), (800, 600)])
        boxes = [line for line in printed if line.strip().startswith("G")]
        for line in boxes:
            x, _, w = int(line.split()[3].split(",")[0]), None, int(
                line.split()[4].split("x")[0])
            self.assertLessEqual(x + w, 800, line)

    def test_one_screen_still_behaves_the_way_it_always_did(self):
        _, _, fake = self._apply([0, 0], screens=[(1920, 1080)])
        self.assertEqual([containment for containment, _ in fake.built], [1])
        self.assertEqual([(c, r) for c, r, _ in fake.geometries],
                         [(1, "1920x1080")])
