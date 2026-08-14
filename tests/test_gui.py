# SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>
#
# SPDX-License-Identifier: MIT

"""The editor, headless.

Skipped entirely when PySide6 is missing, so the suite still runs on a machine
that only has the command line.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

# Must be set before Qt is imported, or it will try for a real display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QModelIndex, Qt
    from PySide6.QtWidgets import QApplication
    from paddocks import gui
    QT = True
except ImportError:  # pragma: no cover - depends on the machine
    QT = False

from paddocks import apps, groups

from .support import write_desktop

CONFIG = """
[[group]]
name = "Dev"
apps = ["code", "gone"]

[[group]]
name = "Web"
apps = ["firefox"]

[[group]]
name = "Media"
apps = []
"""

_app = None


def setUpModule():
    global _app
    if QT:
        _app = QApplication.instance() or QApplication([])


@unittest.skipUnless(QT, "PySide6 is not installed")
class EditorTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)

        applications = root / "applications"
        write_desktop(applications, "code", "Visual Studio Code")
        write_desktop(applications, "firefox", "Firefox")
        write_desktop(applications, "org.kde.krita", "Krita")
        self.index = apps.build([applications])

        self.config_path = root / "paddocks.toml"
        self.config_path.write_text(CONFIG)

        # The editor would otherwise index the real machine.
        self._real_build = gui.apps.build
        gui.apps.build = lambda *a, **k: self.index
        self.addCleanup(lambda: setattr(gui.apps, "build", self._real_build))

        self.editor = gui.Editor(self.config_path)
        self.addCleanup(self.editor.deleteLater)

    def group_names(self):
        return [self.editor.group_list.item(r).data(gui.ROLE).name
                for r in range(self.editor.group_list.count())]

    def app_ids(self):
        return [self.editor.app_list.item(r).data(gui.ROLE)
                for r in range(self.editor.app_list.count())]

    def test_loads_the_groups(self):
        self.assertEqual(self.group_names(), ["Dev", "Web", "Media"])

    def test_selecting_a_group_shows_its_applications(self):
        self.editor.group_list.setCurrentRow(0)
        self.assertEqual(self.app_ids(), ["code", "gone"])

    def test_an_unresolved_id_is_kept_and_marked(self):
        self.editor.group_list.setCurrentRow(0)
        missing = self.editor.app_list.item(1)
        self.assertEqual(missing.data(gui.ROLE), "gone")
        self.assertIn("not installed", missing.text())

    def test_an_unresolved_id_survives_a_save(self):
        self.editor.group_list.setCurrentRow(0)
        self.editor._save()
        reloaded = groups.load_config(self.config_path)
        self.assertEqual(reloaded.groups[0].apps, ["code", "gone"])

    def test_adding_from_the_library_skips_duplicates(self):
        self.editor.group_list.setCurrentRow(1)
        for row in range(self.editor.library.count()):
            item = self.editor.library.item(row)
            if item.data(gui.ROLE) in ("firefox", "org.kde.krita"):
                item.setSelected(True)
        self.editor._add_apps()
        self.assertEqual(self.app_ids(), ["firefox", "org.kde.krita"])

    def test_edits_survive_switching_groups(self):
        self.editor.group_list.setCurrentRow(1)
        for row in range(self.editor.library.count()):
            if self.editor.library.item(row).data(gui.ROLE) == "org.kde.krita":
                self.editor.library.item(row).setSelected(True)
        self.editor._add_apps()
        self.editor.group_list.setCurrentRow(0)
        self.editor.group_list.setCurrentRow(1)
        self.assertEqual(self.app_ids(), ["firefox", "org.kde.krita"])

    def test_duplicate_group_names_are_refused_case_insensitively(self):
        self.assertTrue(self.editor._name_taken("dev"))
        self.assertFalse(self.editor._name_taken("Something else"))

    def test_group_objects_survive_a_drag(self):
        # An InternalMove drag serialises the row through mime data. Python
        # objects in item data have to come back intact, or a dragged group
        # loses its applications.
        item = self.editor.group_list.item(0)
        mime = self.editor.group_list.mimeData([item])
        self.assertTrue(self.editor.group_list.dropMimeData(
            2, mime, Qt.DropAction.MoveAction))
        recovered = self.editor.group_list.item(2).data(gui.ROLE)
        self.assertIsInstance(recovered, groups.Group)
        self.assertEqual(recovered.name, "Dev")
        self.assertEqual(recovered.apps, ["code", "gone"])

    def test_a_drop_inserts_rather_than_overwrites(self):
        # Overwrite mode would silently delete the group landed on.
        self.assertFalse(self.editor.group_list.dragDropOverwriteMode())
        self.assertFalse(self.editor.app_list.dragDropOverwriteMode())

    def test_reordering_changes_the_saved_order_without_losing_a_group(self):
        before = self.group_names()
        self.editor.group_list.model().moveRow(QModelIndex(), 0, QModelIndex(), 3)
        after = self.group_names()
        self.assertNotEqual(before, after)
        self.assertCountEqual(before, after)
        self.assertEqual([g.name for g in self.editor._config().groups], after)

    def test_saving_writes_a_config_that_loads_again(self):
        self.editor.group_list.setCurrentRow(0)
        self.editor.arrangement_box.setCurrentText("grid")
        self.editor.columns_box.setValue(5)
        self.assertTrue(self.editor._save())

        reloaded = groups.load_config(self.config_path)
        self.assertEqual(reloaded.arrangement, "grid")
        self.assertEqual(reloaded.metrics.max_columns, 5)
        self.assertEqual([g.name for g in reloaded.groups], ["Dev", "Web", "Media"])

    def test_saving_is_atomic_and_leaves_no_temp_file(self):
        self.editor._save()
        leftovers = list(self.config_path.parent.glob("*.tmp"))
        self.assertEqual(leftovers, [])

    def test_the_window_icon_loads(self):
        self.assertFalse(gui.paddocks_icon().isNull())
        self.assertIn(gui._colour_scheme(), ("dark", "light"))


if __name__ == "__main__":
    unittest.main()
