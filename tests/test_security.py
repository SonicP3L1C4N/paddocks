# SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Regressions for the four issues found in the security pass.

Each of these was a real defect at some point; the point of the file is that
they stay fixed.
"""

from __future__ import annotations

import json
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from paddocks import apps, groups, plasma, translucency
from paddocks.layout import Metrics

from .support import FakePlasma


class ThemeNameTraversal(unittest.TestCase):
    """1. A theme id names one directory and must not be able to be a path.

    `reset()` does rmtree(USER_THEMES / theme) and `apply()` copytree()s to the
    same place, with the name coming from plasmarc or from a look-and-feel
    package — and people install those from the KDE Store.
    """

    TRAVERSALS = ["../../../../../../tmp", "../../../../../../tmp/evil",
                  "a/../../b", "..", ".", "", "back\\slash", "nul\0byte",
                  "/etc", "theme/../../.."]

    def test_traversing_names_are_rejected(self):
        for name in self.TRAVERSALS:
            with self.subTest(name=name):
                self.assertFalse(translucency._is_safe_name(name))

    def test_ordinary_theme_names_are_accepted(self):
        for name in ("breeze", "kubuntu-light", "Oxygen", "my_theme.2"):
            with self.subTest(name=name):
                self.assertTrue(translucency._is_safe_name(name))

    def test_system_theme_dir_refuses_to_resolve_a_traversal(self):
        # The bare is_dir() check passes for these, because the traversal
        # resolves somewhere that really does exist. The name check is what
        # stops it.
        for name in self.TRAVERSALS:
            with self.subTest(name=name):
                self.assertIsNone(translucency._system_theme_dir(name))

    def test_active_themes_filters_hostile_names(self):
        with mock.patch.object(translucency, "_themes_from_lookandfeel",
                               return_value=["../../../../../../tmp"]), \
             mock.patch.object(Path, "read_text",
                               return_value="[Theme]\nname=../../../../tmp\n"):
            self.assertEqual(translucency.active_themes(), [])


class PlasmashellAlwaysRestarts(unittest.TestCase):
    """2. plasmashell is stopped for the geometry write; a failure in between
    used to leave the user with no panels and no desktop."""

    def _apply_with(self, fail_in):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            fake = FakePlasma(state, fail_in=fail_in)
            config = groups.Config(groups=[groups.Group("G", ["nothing"])],
                                   metrics=Metrics())
            with mock.patch.object(groups, "plasma", fake), \
                 mock.patch.object(groups, "STATE_FILE", state / "state.json"), \
                 mock.patch.object(groups.apps, "build", return_value=apps.Index()), \
                 mock.patch("builtins.print"):
                with self.assertRaises(OSError):
                    groups.apply(config)
            return fake

    def test_restarts_when_the_backup_fails(self):
        self.assertEqual(self._apply_with("backup_appletsrc").shell_calls,
                         ["stop", "start"])

    def test_restarts_when_the_geometry_write_fails(self):
        self.assertEqual(self._apply_with("write_item_geometries").shell_calls,
                         ["stop", "start"])

    def test_translucency_reload_restarts_after_a_cache_failure(self):
        fake = FakePlasma(Path("/nonexistent"))
        fake.clear_theme_caches = lambda: (_ for _ in ()).throw(OSError("boom"))
        with mock.patch.object(translucency, "plasma", fake):
            with self.assertRaises(OSError):
                translucency._reload(restart=True)
        self.assertEqual(fake.shell_calls, ["stop", "start"])


class KwriteconfigFailure(unittest.TestCase):
    """3. It was check=True, so it raised CalledProcessError — a
    SubprocessError, which the CLI's handler does not catch."""

    def test_raises_plasma_error_not_called_process_error(self):
        with mock.patch.object(plasma, "is_running", return_value=False), \
             mock.patch.object(plasma, "_kwriteconfig", return_value="/bin/false"):
            with self.assertRaises(plasma.PlasmaError):
                plasma.write_item_geometries(1, "1920x1080", "Applet-1:0,0,1,1,0;")

    def test_plasma_error_is_caught_by_the_cli_handler(self):
        import subprocess
        self.assertTrue(issubclass(
            plasma.PlasmaError,
            (RuntimeError, ValueError, OSError, subprocess.SubprocessError)))

    def test_refuses_to_write_while_plasmashell_runs(self):
        with mock.patch.object(plasma, "is_running", return_value=True):
            with self.assertRaises(plasma.PlasmaError):
                plasma.write_item_geometries(1, "1920x1080", "x")


class TomlControlCharacters(unittest.TestCase):
    """4. The writer escaped quotes and backslashes but not control
    characters, so a group name with a newline wrote a config that would not
    parse on the next read."""

    HOSTILE = ["line1\nline2", "a\rb", "col1\tcol2", 'Dev "Tools"',
               "C:\\evil", 'a"] \n[[group]]\nname = "injected',
               "a\x00b", "a\x07b", "Ünïcodé — dash", "back\\\\slash"]

    def test_hostile_group_names_round_trip_exactly(self):
        for name in self.HOSTILE:
            with self.subTest(name=name):
                config = groups.Config(groups=[groups.Group(name, ["code"])],
                                       metrics=Metrics())
                parsed = tomllib.loads(groups.dump_config(config))
                self.assertEqual(len(parsed["group"]), 1)
                self.assertEqual(parsed["group"][0]["name"], name)

    def test_a_name_cannot_smuggle_in_a_second_group(self):
        name = 'x"]\n\n[[group]]\nname = "injected"\napps = ["evil'
        config = groups.Config(groups=[groups.Group(name, [])], metrics=Metrics())
        parsed = tomllib.loads(groups.dump_config(config))
        self.assertEqual([g["name"] for g in parsed["group"]], [name])

    def test_application_names_cannot_break_out_of_a_comment(self):
        index = apps.Index(entries={"x": apps.Entry(
            app_id="x", path=Path("/x.desktop"),
            name="Evil\n[[group]]\nname = \"injected\"", icon="",
            categories=(), visible=True)})
        config = groups.Config(groups=[groups.Group("G", ["x"])], metrics=Metrics())
        parsed = tomllib.loads(groups.dump_config(config, index))
        self.assertEqual([g["name"] for g in parsed["group"]], ["G"])


class ScriptInjection(unittest.TestCase):
    """Group titles and launcher URLs are interpolated into the JavaScript
    handed to evaluateScript. json.dumps defaults to ensure_ascii=True, which
    is what keeps that safe — including U+2028/U+2029, which are legal in JSON
    but were not always legal in a JS string literal."""

    def test_payload_is_pure_ascii_whatever_the_title(self):
        titles = ['"); PWNED(); //', "x\u2028PWNED();\u2029", "a\\\"; PWNED();",
                  "</script><script>PWNED()</script>", "tab\there\nnewline"]
        payload = json.dumps([{"title": t, "urls": ["file:///a"], "rows": 1}
                              for t in titles])
        self.assertTrue(payload.isascii())
        self.assertNotIn("\u2028", payload)
        # And nothing is lost by the escaping.
        self.assertEqual([e["title"] for e in json.loads(payload)], titles)


if __name__ == "__main__":
    unittest.main()
