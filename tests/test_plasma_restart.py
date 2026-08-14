# SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Regressions for the shell-restart bug.

`start()` used to spawn plasmashell as a plain child process. A child inherits
its parent's cgroup -- `start_new_session=True` changes the session id, not the
unit -- so the new shell landed in whatever transient `app-*.service` the
desktop had created to launch Paddocks. Those units are
`KillMode=control-group`, which ties the desktop shell's life to the terminal
or menu entry that started us, and leaves `plasma-plasmashell.service` inactive
and no longer describing the running desktop.

Nothing here may spawn a real shell, so `subprocess.Popen` is mocked in every
test that reaches the fallback path.
"""

from __future__ import annotations

import unittest
from unittest import mock

from paddocks import plasma


def _ok(stdout: str = "up"):
    return mock.Mock(returncode=0, stdout=stdout, stderr="")


class UnitDetection(unittest.TestCase):
    def test_no_systemctl_means_no_unit(self):
        with mock.patch.object(plasma.shutil, "which", return_value=None):
            self.assertFalse(plasma.unit_is_known())

    def test_unit_is_known_when_systemctl_cat_succeeds(self):
        with mock.patch.object(plasma.shutil, "which",
                               return_value="/usr/bin/systemctl"), \
             mock.patch.object(plasma.subprocess, "run", return_value=_ok()):
            self.assertTrue(plasma.unit_is_known())

    def test_unit_is_unknown_when_systemctl_cat_fails(self):
        with mock.patch.object(plasma.shutil, "which",
                               return_value="/usr/bin/systemctl"), \
             mock.patch.object(plasma.subprocess, "run",
                               return_value=mock.Mock(returncode=1)):
            self.assertFalse(plasma.unit_is_known())


class StartPrefersSystemd(unittest.TestCase):
    def test_starts_the_unit_and_never_spawns_a_child(self):
        with mock.patch.object(plasma, "unit_is_known", return_value=True), \
             mock.patch.object(plasma.shutil, "which",
                               return_value="/usr/bin/systemctl"), \
             mock.patch.object(plasma.subprocess, "run",
                               return_value=_ok()) as run, \
             mock.patch.object(plasma.subprocess, "Popen") as popen:
            plasma.start()

        popen.assert_not_called()
        command = run.call_args[0][0]
        self.assertEqual(command[1:], ["--user", "start", plasma.PLASMA_UNIT])

    def test_falls_back_to_spawning_when_there_is_no_unit(self):
        with mock.patch.object(plasma, "unit_is_known", return_value=False), \
             mock.patch.object(plasma, "_qdbus", return_value="/bin/true"), \
             mock.patch.object(plasma.subprocess, "run", return_value=_ok()), \
             mock.patch.object(plasma.subprocess, "Popen") as popen:
            plasma.start()

        popen.assert_called_once()
        self.assertEqual(popen.call_args[0][0], ["plasmashell"])

    def test_falls_back_when_the_unit_will_not_start(self):
        """A masked or broken unit must leave the user with a desktop."""
        responses = [mock.Mock(returncode=1, stdout="", stderr="masked")]
        responses += [_ok()] * 5

        with mock.patch.object(plasma, "unit_is_known", return_value=True), \
             mock.patch.object(plasma, "_qdbus", return_value="/bin/true"), \
             mock.patch.object(plasma.shutil, "which",
                               return_value="/usr/bin/systemctl"), \
             mock.patch.object(plasma.subprocess, "run",
                               side_effect=responses), \
             mock.patch.object(plasma.subprocess, "Popen") as popen:
            plasma.start()

        popen.assert_called_once()


class CgroupInheritance(unittest.TestCase):
    """The premise the fix rests on, asserted rather than assumed."""

    def test_start_new_session_does_not_change_the_cgroup(self):
        import subprocess
        from pathlib import Path

        cgroup = Path("/proc/self/cgroup")
        if not cgroup.exists():
            self.skipTest("no cgroup information on this platform")

        mine = cgroup.read_text().strip()
        child = subprocess.Popen(["sleep", "5"], start_new_session=True)
        try:
            theirs = Path(f"/proc/{child.pid}/cgroup").read_text().strip()
        finally:
            child.kill()
            child.wait()

        self.assertEqual(mine, theirs)


if __name__ == "__main__":
    unittest.main()
