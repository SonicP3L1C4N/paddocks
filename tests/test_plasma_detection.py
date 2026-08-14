# SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>
#
# SPDX-License-Identifier: MIT

"""How `is_running` decides there is a shell.

It used to be `pgrep -x plasmashell`, which answers a different question than
the one the callers ask: it matches any user's shell on a shared machine, and
from inside a sandbox it sees no host processes and reports False while a
shell is running. That False is what `write_item_geometries` checks before it
writes, so getting it wrong scrambles the desktop layout rather than merely
misreporting.
"""

from __future__ import annotations

import unittest
from unittest import mock

from paddocks import plasma


class IsRunning(unittest.TestCase):
    def _answer(self, stdout: str, returncode: int = 0):
        return mock.patch.object(
            plasma.subprocess, "run",
            return_value=mock.Mock(returncode=returncode, stdout=stdout,
                                   stderr=""),
        )

    def test_true_when_the_name_has_an_owner(self):
        with mock.patch.object(plasma, "_qdbus", return_value="/bin/true"), \
             self._answer("true\n"):
            self.assertTrue(plasma.is_running())

    def test_false_when_the_name_is_unowned(self):
        with mock.patch.object(plasma, "_qdbus", return_value="/bin/true"), \
             self._answer("false\n"):
            self.assertFalse(plasma.is_running())

    def test_asks_the_session_bus_not_pgrep(self):
        with mock.patch.object(plasma, "_qdbus", return_value="/bin/true"), \
             self._answer("true\n") as run:
            plasma.is_running()

        command = run.call_args[0][0]
        self.assertNotIn("pgrep", command)
        self.assertIn("org.freedesktop.DBus.NameHasOwner", command)
        self.assertIn("org.kde.plasmashell", command)

    def test_raises_rather_than_answering_false_when_it_cannot_ask(self):
        """A False here is what lets a geometry write go ahead."""
        with mock.patch.object(plasma, "_qdbus", return_value="/bin/true"), \
             self._answer("", returncode=1):
            with self.assertRaises(plasma.PlasmaError):
                plasma.is_running()

    def test_missing_qdbus_is_an_error_too(self):
        with mock.patch.object(plasma.shutil, "which", return_value=None):
            with self.assertRaises(plasma.PlasmaError):
                plasma.is_running()

    def test_the_geometry_guard_still_refuses_while_a_shell_runs(self):
        with mock.patch.object(plasma, "_qdbus", return_value="/bin/true"), \
             self._answer("true\n"):
            with self.assertRaises(plasma.PlasmaError):
                plasma.write_item_geometries(1, "1920x1080", "Applet-1:0,0,1,1,0;")


if __name__ == "__main__":
    unittest.main()
