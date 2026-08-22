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
    from PySide6.QtWidgets import QApplication, QLabel
    from paddocks import gui
    QT = True
except ImportError:  # pragma: no cover - depends on the machine
    QT = False

from paddocks import apps, groups
from paddocks import __version__

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
class EditorFixture(unittest.TestCase):
    """Setup shared by the editor suites; holds no tests of its own."""

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

        # ...and ask the running plasmashell for its screens. No test may talk
        # to the real shell, so the screen list is faked the same way.
        self._real_screens = gui.plasma.screens
        self.addCleanup(lambda: setattr(gui.plasma, "screens", self._real_screens))
        self.set_screens([(1920, 1080), (1280, 1024)])

        self.editor = self.make_editor()

    def set_screens(self, sizes, fail=False):
        """`sizes` is [(width, height), ...]; containment ids are index + 1."""
        def screens():
            if fail:
                raise gui.plasma.PlasmaError("no plasmashell in this session")
            return [gui.plasma.Screen(i, w, h, i + 1)
                    for i, (w, h) in enumerate(sizes)]
        gui.plasma.screens = screens

    def make_editor(self):
        editor = gui.Editor(self.config_path)
        self.addCleanup(editor.deleteLater)
        return editor

    def screen_entries(self):
        box = self.editor.screen_box
        return [(box.itemText(i), box.itemData(i)) for i in range(box.count())]

    def group_names(self):
        return [self.editor.group_list.item(r).data(gui.ROLE).name
                for r in range(self.editor.group_list.count())]

    def app_ids(self):
        return [self.editor.app_list.item(r).data(gui.ROLE)
                for r in range(self.editor.app_list.count())]


@unittest.skipUnless(QT, "PySide6 is not installed")
class EditorTest(EditorFixture):
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


@unittest.skipUnless(QT, "PySide6 is not installed")
class ScreenPicker(EditorFixture):
    """Choosing which monitor a group is built on.

    The picker drives the same `screen` key the TOML has, so the thing worth
    testing is the edges: a group configured for a monitor that is not plugged
    in must keep it, and the editor has to open at all when there is no
    plasmashell to ask.
    """

    def test_it_offers_the_screens_plasma_reports(self):
        self.editor.group_list.setCurrentRow(0)
        self.assertEqual(self.screen_entries(),
                         [("0 — 1920×1080", 0), ("1 — 1280×1024", 1)])

    def test_it_shows_the_screen_the_group_is_on(self):
        self.config_path.write_text(CONFIG + '\nscreen = 1\n')
        self.editor = self.make_editor()
        self.editor.group_list.setCurrentRow(2)
        self.assertEqual(self.editor.screen_box.currentData(), 1)

    def test_choosing_a_screen_moves_the_group(self):
        self.editor.group_list.setCurrentRow(0)
        self.editor.screen_box.setCurrentIndex(1)
        self.assertEqual(self.editor._current_group().screen, 1)
        self.assertTrue(self.editor.dirty)

    def test_the_choice_survives_a_save(self):
        self.editor.group_list.setCurrentRow(0)
        self.editor.screen_box.setCurrentIndex(1)
        self.editor._save()
        reloaded = groups.load_config(self.config_path)
        self.assertEqual([g.screen for g in reloaded.groups], [1, 0, 0])

    def test_switching_groups_does_not_mark_the_config_dirty(self):
        """Filling the picker must not read as the user having chosen."""
        self.editor.group_list.setCurrentRow(0)
        self.editor.group_list.setCurrentRow(1)
        self.assertFalse(self.editor.dirty)

    def test_a_group_keeps_a_screen_that_is_not_plugged_in(self):
        """Unplugging a monitor is not a decision to move what was on it."""
        self.config_path.write_text(CONFIG + '\nscreen = 3\n')
        self.set_screens([(1920, 1080)])
        self.editor = self.make_editor()
        self.editor.group_list.setCurrentRow(2)
        self.assertEqual(self.editor.screen_box.currentData(), 3)
        self.assertIn("not connected", self.editor.screen_box.currentText())
        self.editor._save()
        self.assertEqual(groups.load_config(self.config_path).groups[2].screen, 3)

    def test_the_editor_opens_with_no_plasmashell_to_ask(self):
        self.set_screens([], fail=True)
        self.editor = self.make_editor()
        self.editor.group_list.setCurrentRow(0)
        self.assertEqual(self.screen_entries(), [("screen 0", 0)])

    def test_the_group_list_says_which_screen_when_it_is_not_the_first(self):
        self.config_path.write_text(CONFIG + '\nscreen = 1\n')
        self.editor = self.make_editor()
        labels = [self.editor.group_list.item(r).text()
                  for r in range(self.editor.group_list.count())]
        self.assertEqual(labels, ["Dev", "Web", "Media   · screen 1"])

    def test_one_screen_is_not_worth_labelling(self):
        self.set_screens([(1920, 1080)])
        self.editor = self.make_editor()
        self.assertEqual(self.editor.group_list.item(0).text(), "Dev")


@unittest.skipUnless(QT, "PySide6 is not installed")
class AboutTest(EditorFixture):
    """Which version is running, and the block a bug report needs."""

    def setUp(self):
        super().setUp()
        # Like the screen list, the Plasma version comes from the real shell,
        # which no test may talk to.
        self._real_version = gui.plasma.version
        gui.plasma.version = lambda: "6.4.5"
        self.addCleanup(
            lambda: setattr(gui.plasma, "version", self._real_version))

    def status_labels(self):
        return [w.text() for w in self.editor.statusBar().findChildren(QLabel)]

    def test_the_version_shows_without_opening_anything(self):
        self.assertIn(f"Paddocks {__version__}", self.status_labels())

    def test_the_menu_offers_about(self):
        texts = [action.text() for action in self.editor.menu.actions()]
        self.assertIn("&About Paddocks", texts)

    def test_the_dialog_names_the_version(self):
        about = gui.AboutDialog(self.editor, self.config_path)
        self.addCleanup(about.deleteLater)
        self.assertIn(__version__, about.details)

    def test_the_details_carry_what_a_bug_report_needs(self):
        details = gui.environment_report(self.config_path)
        self.assertIn("6.4.5", details)
        self.assertIn(str(self.config_path), details)
        self.assertIn("Qt", details)
        self.assertIn("Python", details)

    def test_no_plasmashell_to_ask_is_said_rather_than_left_blank(self):
        gui.plasma.version = lambda: ""
        self.assertIn("not detected", gui.environment_report(self.config_path))

    def test_copying_the_details_puts_them_on_the_clipboard(self):
        about = gui.AboutDialog(self.editor, self.config_path)
        self.addCleanup(about.deleteLater)
        about._copy()
        self.assertEqual(QApplication.clipboard().text(), about.details)
