"""Reading and writing the TOML.

Every one of these mistakes used to be silent: unknown settings were filtered
out on the way to Metrics, and a group with no name came out as a KeyError
traceback.
"""

from __future__ import annotations

import tempfile
import tomllib
import unittest
from pathlib import Path

from paddocks import groups
from paddocks.layout import Metrics

VALID = """
[settings]
arrangement = "grid"
align = "left"
cell = 150

[[group]]
name = "Dev"
apps = ["code", "org.kde.konsole"]

[[group]]
name = "Web"
apps = ["firefox"]
"""


class LoadConfig(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paddocks.toml"
            path.write_text(text)
            return groups.load_config(path)

    def assertRejected(self, text, *expected):
        with self.assertRaises(groups.ConfigError) as caught:
            self.load(text)
        for fragment in expected:
            self.assertIn(fragment, str(caught.exception))

    def test_a_valid_config_loads(self):
        config = self.load(VALID)
        self.assertEqual([g.name for g in config.groups], ["Dev", "Web"])
        self.assertEqual(config.groups[0].apps, ["code", "org.kde.konsole"])
        self.assertEqual(config.arrangement, "grid")
        self.assertEqual(config.metrics.align, "left")
        self.assertEqual(config.metrics.cell, 150)

    def test_defaults_when_settings_are_absent(self):
        config = self.load('[[group]]\nname = "A"\napps = []')
        self.assertEqual(config.arrangement, "row")
        self.assertEqual(config.metrics, Metrics())

    def test_misspelled_setting_is_named_and_suggested(self):
        self.assertRejected('[settings]\nmax_column = 3\n[[group]]\nname="A"',
                            "unknown setting", "max_column", "max_columns")

    def test_unknown_setting_lists_the_known_ones(self):
        self.assertRejected('[settings]\ncolour = "red"\n[[group]]\nname="A"',
                            "unknown setting", "colour", "max_columns")

    def test_misspelled_table_is_named_and_suggested(self):
        self.assertRejected('[[groups]]\nname = "A"',
                            "unknown top-level key", "groups", "group")

    def test_unknown_group_key(self):
        self.assertRejected('[[group]]\nname = "A"\napp = ["code"]',
                            "unknown group key", "app")

    def test_bad_arrangement(self):
        self.assertRejected('[settings]\narrangement = "rows"\n[[group]]\nname="A"',
                            "arrangement", "row, grid, column")

    def test_bad_align(self):
        self.assertRejected('[settings]\nalign = "middle"\n[[group]]\nname="A"',
                            "align", "center, left")

    def test_metric_of_the_wrong_type(self):
        self.assertRejected('[settings]\ncell = "140"\n[[group]]\nname="A"',
                            "cell must be a whole number")

    def test_group_without_a_name(self):
        self.assertRejected('[[group]]\napps = ["code"]', "has no name")

    def test_apps_that_is_not_a_list_of_strings(self):
        self.assertRejected('[[group]]\nname="A"\napps = "code"',
                            "must be a list of strings")
        self.assertRejected('[[group]]\nname="A"\napps = [1, 2]',
                            "must be a list of strings")

    def test_no_groups_at_all(self):
        self.assertRejected('[settings]\narrangement = "row"', "no [[group]]")

    def test_duplicate_group_names_are_refused_case_insensitively(self):
        self.assertRejected('[[group]]\nname="Dev"\napps=[]\n'
                            '[[group]]\nname="dev"\napps=[]',
                            "share a name", "must be unique")

    def test_malformed_toml_is_a_config_error_not_a_traceback(self):
        self.assertRejected('[[group]\nname = "A"', "not valid TOML")

    def test_a_repeat_names_the_group_it_is_actually_in(self):
        config = self.load('[[group]]\nname="A"\napps=["x"]\n'
                           '[[group]]\nname="B"\napps=["x","x"]')
        self.assertIn("x is listed twice in B", config.warnings)
        self.assertNotIn("x is listed twice in A", config.warnings)

    def test_a_repeat_is_reported_once_however_many_times_it_appears(self):
        config = self.load('[[group]]\nname="A"\napps=["x","x","x"]')
        self.assertEqual(sum("listed twice" in w for w in config.warnings), 1)

    def test_warnings_are_collected_not_raised(self):
        config = self.load('[[group]]\nname="A"\napps=["x","x"]\n'
                           '[[group]]\nname="B"\napps=[]\n'
                           '[[group]]\nname="C"\napps=["x"]')
        joined = " | ".join(config.warnings)
        self.assertIn("listed twice", joined)
        self.assertIn("lists no apps", joined)
        self.assertIn("appears in 2 groups", joined)


class DumpConfig(unittest.TestCase):
    def test_round_trips_through_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.toml"
            path.write_text(VALID)
            original = groups.load_config(path)

            path.write_text(groups.dump_config(original))
            again = groups.load_config(path)

        self.assertEqual([(g.name, g.apps) for g in original.groups],
                         [(g.name, g.apps) for g in again.groups])
        self.assertEqual(original.arrangement, again.arrangement)
        self.assertEqual(original.metrics, again.metrics)

    def test_only_non_default_metrics_are_written(self):
        config = groups.Config(groups=[groups.Group("A", [])],
                               metrics=Metrics(cell=150))
        text = groups.dump_config(config)
        self.assertIn("cell = 150", text)
        self.assertNotIn("header =", text)
        self.assertNotIn("min_width =", text)

    def test_arrangement_and_align_are_always_written(self):
        text = groups.dump_config(groups.Config(groups=[groups.Group("A", [])]))
        self.assertIn('arrangement = "row"', text)
        self.assertIn('align = "center"', text)

    def test_an_empty_group_survives(self):
        text = groups.dump_config(groups.Config(groups=[groups.Group("A", [])]))
        self.assertIn("apps = []", text)
        self.assertEqual(tomllib.loads(text)["group"][0]["apps"], [])

    def test_booleans_render_as_toml_not_python(self):
        self.assertEqual(groups._toml_value(True), "true")
        self.assertEqual(groups._toml_value(False), "false")


if __name__ == "__main__":
    unittest.main()
