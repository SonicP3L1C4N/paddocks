"""`strict` as a config setting, and how it combines with the flag.

The point of having it in the config is that a hand-written .desktop file
breaks silently when whatever it points at moves, and the app then just
quietly stops appearing in its group. Strict turns that into a refusal.

Because the setting is invisible in the command the user typed, the command
line has to be able to override it in both directions, and the failure has to
say which of the two turned it on.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from paddocks import apps, groups
from paddocks.layout import Metrics

from .support import FakePlasma

MINIMAL = """
[[group]]
name = "G"
apps = ["nothing"]
"""


class ParsingTheSetting(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paddocks.toml"
            path.write_text(text)
            return groups.load_config(path)

    def test_defaults_to_off(self):
        self.assertFalse(self.load(MINIMAL).strict)

    def test_reads_true(self):
        self.assertTrue(self.load("[settings]\nstrict = true\n" + MINIMAL).strict)

    def test_reads_false(self):
        self.assertFalse(self.load("[settings]\nstrict = false\n" + MINIMAL).strict)

    def test_rejects_a_non_boolean(self):
        with self.assertRaises(groups.ConfigError) as caught:
            self.load('[settings]\nstrict = "yes"\n' + MINIMAL)
        self.assertIn("must be true or false", str(caught.exception))

    def test_it_is_an_accepted_setting_name(self):
        """A typo'd setting is rejected, so `strict` must be whitelisted."""
        self.assertIn("strict", groups.SETTINGS_KEYS)


class FlagBeatsConfig(unittest.TestCase):
    """`strict=None` means the command line said nothing."""

    def _apply(self, config_strict, flag):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            config = groups.Config(groups=[groups.Group("G", ["nothing"])],
                                   metrics=Metrics(), strict=config_strict)
            with mock.patch.object(groups, "plasma", FakePlasma(state)), \
                 mock.patch.object(groups, "STATE_FILE", state / "state.json"), \
                 mock.patch.object(groups.apps, "build",
                                   return_value=apps.Index()), \
                 mock.patch("builtins.print"):
                # "nothing" resolves to nothing, so strict decides the outcome.
                try:
                    groups.apply(config, strict=flag)
                except ValueError as exc:
                    return str(exc)
            return None

    def test_config_on_and_no_flag_refuses(self):
        self.assertIn("did not resolve", self._apply(True, None))

    def test_config_off_and_no_flag_builds(self):
        self.assertIsNone(self._apply(False, None))

    def test_flag_turns_it_on_over_a_config_that_says_off(self):
        self.assertIn("did not resolve", self._apply(False, True))

    def test_no_strict_turns_it_off_over_a_config_that_says_on(self):
        self.assertIsNone(self._apply(True, False))

    def test_the_message_names_the_config_when_the_config_set_it(self):
        self.assertIn("in the config", self._apply(True, None))

    def test_the_message_names_the_flag_when_the_flag_set_it(self):
        self.assertIn("--strict", self._apply(False, True))


class CommandLine(unittest.TestCase):
    """The real parser, not a copy of it."""

    def strict_for(self, *argv):
        from paddocks import cli
        return cli.build_parser().parse_args(["apply", *argv]).strict

    def test_saying_nothing_leaves_it_to_the_config(self):
        self.assertIsNone(self.strict_for())

    def test_strict_is_true(self):
        self.assertTrue(self.strict_for("--strict"))
        self.assertTrue(self.strict_for("-s"))

    def test_no_strict_is_false_not_none(self):
        """False and None must stay distinguishable, or the override is lost."""
        self.assertIs(self.strict_for("--no-strict"), False)


class TheEditorOptsOut(unittest.TestCase):
    """Strict guards against a silent drop; the editor shows misses in red,
    so it applies regardless rather than refusing with no way forward."""

    def test_the_worker_passes_strict_false(self):
        try:
            from paddocks import gui
        except ImportError:
            self.skipTest("PyQt6 is not installed")

        config = groups.Config(groups=[groups.Group("G", ["nothing"])],
                               metrics=Metrics(), strict=True)
        with mock.patch.object(groups, "apply") as applied:
            gui.Worker(config, dry_run=True).run()

        self.assertIs(applied.call_args.kwargs["strict"], False)


if __name__ == "__main__":
    unittest.main()
