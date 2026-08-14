# SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Folder groups: a group that shows a directory instead of launchers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from paddocks import apps, groups
from paddocks.layout import (FOLDER_CELLS, FOLDER_MIN_HEIGHT, FOLDER_MIN_WIDTH,
                             Metrics, size_for, solve)

from .support import FakePlasma, write_desktop


class ConfigParsing(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def load(self, text: str) -> groups.Config:
        path = self.dir / "paddocks.toml"
        path.write_text(text)
        return groups.load_config(path)

    def test_a_path_makes_a_folder_group(self):
        config = self.load(f'[[group]]\nname = "Docs"\npath = "{self.dir}"\n')
        group = config.groups[0]
        self.assertTrue(group.is_folder)
        self.assertEqual(group.apps, [])
        self.assertEqual(group.expanded_path(), self.dir)

    def test_an_apps_group_is_not_a_folder_group(self):
        config = self.load('[[group]]\nname = "Dev"\napps = ["code"]\n')
        self.assertFalse(config.groups[0].is_folder)
        self.assertIsNone(config.groups[0].expanded_path())

    def test_apps_and_path_together_are_rejected(self):
        with self.assertRaises(groups.ConfigError) as caught:
            self.load('[[group]]\nname = "Both"\napps = ["code"]\npath = "/tmp"\n')
        self.assertIn("not both", str(caught.exception))

    def test_an_empty_path_is_rejected(self):
        with self.assertRaises(groups.ConfigError):
            self.load('[[group]]\nname = "Blank"\npath = "   "\n')

    def test_tilde_and_vars_expand(self):
        config = self.load('[[group]]\nname = "Home"\npath = "~/Downloads"\n')
        self.assertEqual(config.groups[0].expanded_path(),
                         Path.home() / "Downloads")

    def test_a_relative_path_is_made_absolute(self):
        # Folder View needs a URL, and Path.as_uri() refuses a relative path.
        config = self.load('[[group]]\nname = "Rel"\npath = "somewhere"\n')
        self.assertTrue(config.groups[0].expanded_path().is_absolute())

    def test_cells_defaults_and_overrides(self):
        default = self.load(f'[[group]]\nname = "D"\npath = "{self.dir}"\n')
        self.assertEqual(default.groups[0].cells, FOLDER_CELLS)
        bigger = self.load(
            f'[[group]]\nname = "D"\npath = "{self.dir}"\ncells = 12\n')
        self.assertEqual(bigger.groups[0].cells, 12)

    def test_cells_without_a_path_is_rejected(self):
        with self.assertRaises(groups.ConfigError) as caught:
            self.load('[[group]]\nname = "Apps"\napps = ["code"]\ncells = 4\n')
        self.assertIn("no `path`", str(caught.exception))

    def test_cells_must_be_a_positive_number(self):
        for bad in ("0", "-3", "true", '"eight"'):
            with self.subTest(cells=bad), self.assertRaises(groups.ConfigError):
                self.load(
                    f'[[group]]\nname = "D"\npath = "{self.dir}"\ncells = {bad}\n')

    def test_a_missing_folder_warns_rather_than_failing(self):
        config = self.load(
            f'[[group]]\nname = "Gone"\npath = "{self.dir / "nope"}"\n')
        self.assertTrue(any("does not exist" in w for w in config.warnings))

    def test_a_file_where_a_folder_was_meant_warns(self):
        target = self.dir / "notadir.txt"
        target.write_text("")
        config = self.load(f'[[group]]\nname = "F"\npath = "{target}"\n')
        self.assertTrue(any("is a file" in w for w in config.warnings))

    def test_a_folder_group_is_not_warned_for_listing_no_apps(self):
        config = self.load(f'[[group]]\nname = "Docs"\npath = "{self.dir}"\n')
        self.assertFalse(any("lists no apps" in w for w in config.warnings))


class Sizing(unittest.TestCase):
    def test_a_folder_is_floored_at_folder_views_minimum(self):
        w, h, _ = size_for(1, Metrics(), folder=True)
        self.assertGreaterEqual(w, FOLDER_MIN_WIDTH)
        self.assertGreaterEqual(h, FOLDER_MIN_HEIGHT)

    def test_an_app_group_is_not_floored_that_high(self):
        w, h, _ = size_for(1, Metrics())
        self.assertLess(w, FOLDER_MIN_WIDTH)
        self.assertLess(h, FOLDER_MIN_HEIGHT)

    def test_a_full_folder_matches_an_app_group_of_the_same_cells(self):
        # Folder groups should share the visual rhythm, not sit slightly off it.
        self.assertEqual(size_for(8, Metrics(), folder=True),
                         size_for(8, Metrics()))

    def test_solve_accepts_the_two_item_form(self):
        boxes = solve([("A", 4), ("B", 4)], (1920, 1080), Metrics(), "row")
        self.assertEqual(len(boxes), 2)

    def test_solve_sizes_a_flagged_group_as_a_folder(self):
        plain = solve([("A", 1)], (1920, 1080), Metrics(), "row")[0]
        folder = solve([("A", 1, True)], (1920, 1080), Metrics(), "row")[0]
        self.assertGreater(folder.w, plain.w)
        self.assertGreaterEqual(folder.w, FOLDER_MIN_WIDTH)


class Applying(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        (self.dir / "shown").mkdir()

        apps_dir = self.dir / "applications"
        apps_dir.mkdir()
        write_desktop(apps_dir, "code", name="Code")

        self.fake = FakePlasma(self.dir)
        for patched in (
            mock.patch.object(groups, "plasma", self.fake),
            mock.patch.object(groups, "STATE_FILE", self.dir / "state.json"),
            mock.patch.object(groups.apps, "build",
                              return_value=apps.build([apps_dir])),
            mock.patch("builtins.print"),
        ):
            patched.start()
            self.addCleanup(patched.stop)

    def config(self) -> groups.Config:
        return groups.Config(groups=[
            groups.Group("Dev", ["code"]),
            groups.Group("Shown", [], path=str(self.dir / "shown")),
        ])

    def test_each_group_asks_for_the_right_plugin(self):
        groups.apply(self.config())
        kinds = [s["kind"] for s in self.fake.specs]
        self.assertEqual(kinds, ["apps", "folder"])

    def test_the_folder_spec_carries_a_file_url_and_the_group_name(self):
        groups.apply(self.config())
        folder = self.fake.specs[1]
        self.assertEqual(folder["title"], "Shown")
        self.assertEqual(folder["url"], (self.dir / "shown").as_uri())
        self.assertTrue(folder["url"].startswith("file://"))

    def test_an_unresolved_launcher_does_not_implicate_a_folder_group(self):
        config = groups.Config(groups=[
            groups.Group("Shown", [], path=str(self.dir / "shown"))])
        # strict trips on missing launchers; a folder group has none to miss.
        groups.apply(config, strict=True)
        self.assertEqual(self.fake.specs[0]["kind"], "folder")


class RoundTrip(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_a_folder_group_survives_a_dump_and_reload(self):
        original = groups.Config(groups=[
            groups.Group("Dev", ["code"]),
            groups.Group("Docs", [], path="~/Documents", cells=12),
        ])
        path = self.dir / "paddocks.toml"
        path.write_text(groups.dump_config(original))
        reloaded = groups.load_config(path)

        self.assertEqual(reloaded.groups[0].apps, ["code"])
        self.assertFalse(reloaded.groups[0].is_folder)
        self.assertEqual(reloaded.groups[1].path, "~/Documents")
        self.assertEqual(reloaded.groups[1].cells, 12)

    def test_a_default_cells_is_not_written_out(self):
        text = groups.dump_config(groups.Config(groups=[
            groups.Group("Docs", [], path="~/Documents")]))
        self.assertIn('path = "~/Documents"', text)
        self.assertNotIn("cells", text)

    def test_a_folder_group_is_not_written_as_an_empty_app_group(self):
        # The failure this guards: `apps = []` alongside no path would turn a
        # folder group into an empty box on the next apply.
        text = groups.dump_config(groups.Config(groups=[
            groups.Group("Docs", [], path="~/Documents")]))
        self.assertNotIn("apps = []", text)


if __name__ == "__main__":
    unittest.main()
