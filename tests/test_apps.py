"""The .desktop index: matching config ids to installed applications.

Built against fixture directories rather than the real system, so the results
do not depend on what happens to be installed on the machine running them.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paddocks import apps

from .support import write_desktop


class IndexFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.first = self.root / "first"
        self.second = self.root / "second"
        self.addCleanup(self._tmp.cleanup)

    def build(self):
        return apps.build([self.first, self.second])


class Resolving(IndexFixture):
    def test_exact_id_wins(self):
        write_desktop(self.first, "code", "Visual Studio Code")
        entry, how = self.build().resolve("code")
        self.assertEqual((entry.app_id, how), ("code", "exact"))

    def test_the_desktop_suffix_is_optional(self):
        write_desktop(self.first, "code", "Visual Studio Code")
        entry, _ = self.build().resolve("code.desktop")
        self.assertEqual(entry.app_id, "code")

    def test_reverse_dns_tail(self):
        write_desktop(self.first, "org.kde.krita", "Krita")
        entry, how = self.build().resolve("krita")
        self.assertEqual((entry.app_id, how), ("org.kde.krita", "alias"))

    def test_snap_style_suffix(self):
        write_desktop(self.first, "firefox_firefox", "Firefox")
        entry, how = self.build().resolve("firefox")
        self.assertEqual((entry.app_id, how), ("firefox_firefox", "alias"))

    def test_application_name(self):
        write_desktop(self.first, "com.obsproject.Studio", "OBS Studio")
        entry, _ = self.build().resolve("obs studio")
        self.assertEqual(entry.app_id, "com.obsproject.Studio")

    def test_a_visible_entry_beats_a_hidden_one_for_the_same_alias(self):
        # krita_brush.desktop is a hidden file-association entry also called
        # "Krita". Sorted first, it used to take the alias on nothing but
        # alphabetical luck.
        write_desktop(self.first, "krita_brush", "Krita", no_display=True)
        write_desktop(self.first, "org.kde.krita", "Krita")
        entry, _ = self.build().resolve("krita")
        self.assertEqual(entry.app_id, "org.kde.krita")

    def test_earlier_directories_win(self):
        write_desktop(self.first, "code", "User Code")
        write_desktop(self.second, "code", "System Code")
        self.assertEqual(self.build().resolve("code")[0].name, "User Code")

    def test_a_miss_returns_nothing(self):
        write_desktop(self.first, "code", "Visual Studio Code")
        entry, how = self.build().resolve("nothing-like-this")
        self.assertIsNone(entry)
        self.assertEqual(how, "")


class Suggesting(IndexFixture):
    def test_a_near_miss_is_suggested(self):
        write_desktop(self.first, "code", "Visual Studio Code")
        self.assertIn("code", self.build().suggest("vscode"))

    def test_a_short_query_falls_back_to_substring(self):
        # difflib scores whole strings, so "obs" against a long reverse-DNS id
        # scores near zero however obviously it is the thing meant.
        write_desktop(self.first, "com.obsproject.Studio", "OBS Studio")
        self.assertEqual(self.build().suggest("obs"), ["com.obsproject.Studio"])

    def test_suggestions_are_real_ids_not_aliases(self):
        write_desktop(self.first, "org.kde.krita", "Krita")
        for suggestion in self.build().suggest("krita"):
            self.assertIn(suggestion, self.build().entries)

    def test_nothing_similar_suggests_nothing(self):
        write_desktop(self.first, "code", "Visual Studio Code")
        self.assertEqual(self.build().suggest("zzzzzzzz"), [])


class Visibility(IndexFixture):
    def test_hidden_kinds_are_left_out(self):
        write_desktop(self.first, "shown", "Shown")
        write_desktop(self.first, "nodisplay", "No", no_display=True)
        write_desktop(self.first, "hidden", "Hid", hidden=True)
        write_desktop(self.first, "gnomeonly", "G", only_show_in="GNOME")
        write_desktop(self.first, "link", "L", entry_type="Link")
        self.assertEqual([e.app_id for e in self.build().visible()], ["shown"])

    def test_kde_only_entries_are_kept(self):
        write_desktop(self.first, "kdeonly", "K", only_show_in="KDE")
        self.assertEqual([e.app_id for e in self.build().visible()], ["kdeonly"])

    def test_hidden_entries_can_still_be_referenced_by_exact_id(self):
        write_desktop(self.first, "nodisplay", "No", no_display=True)
        entry, how = self.build().resolve("nodisplay")
        self.assertEqual(how, "exact")
        self.assertFalse(entry.visible)


class Grouping(IndexFixture):
    def group_of(self, categories):
        write_desktop(self.first, "x", "X", categories=categories)
        return apps.group_for(self.build().entries["x"])

    def test_categories_map_to_group_names(self):
        self.assertEqual(self.group_of("Graphics;2DGraphics;"), "Graphics")
        self.assertEqual(self.group_of("AudioVideo;Recorder;"), "Media")
        self.assertEqual(self.group_of("Network;WebBrowser;"), "Internet")

    def test_the_first_matching_category_wins(self):
        # Steam is Network;FileTransfer;Game and belongs under Games; KiCad is
        # Development;Electronics and belongs under Development.
        self.assertEqual(self.group_of("Network;FileTransfer;Game;"), "Games")
        self.assertEqual(self.group_of("Development;Electronics;"), "Development")

    def test_no_categories_falls_through_to_other(self):
        self.assertEqual(self.group_of(""), apps.OTHER_GROUP)


class Parsing(IndexFixture):
    def test_localised_names_are_ignored(self):
        (self.first).mkdir(parents=True, exist_ok=True)
        (self.first / "x.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Plain\nName[de]=Deutsch\n")
        self.assertEqual(self.build().entries["x"].name, "Plain")

    def test_keys_outside_the_desktop_entry_group_are_ignored(self):
        (self.first).mkdir(parents=True, exist_ok=True)
        (self.first / "x.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Real\n"
            "[Desktop Action New]\nName=Action\n")
        self.assertEqual(self.build().entries["x"].name, "Real")

    def test_a_file_without_the_group_is_skipped(self):
        (self.first).mkdir(parents=True, exist_ok=True)
        (self.first / "junk.desktop").write_text("not a desktop file\n")
        self.assertNotIn("junk", self.build().entries)

    def test_the_launcher_url_is_not_resolved_through_symlinks(self):
        # Flatpak's exports directory is a symlink farm into content-addressed
        # paths; resolving would bake in a commit hash that changes on update.
        real = write_desktop(self.second, "target", "Target")
        self.first.mkdir(parents=True, exist_ok=True)
        link = self.first / "app.desktop"
        link.symlink_to(real)
        entry, _ = self.build().resolve("app")
        self.assertEqual(entry.url, link.as_uri())
        self.assertNotEqual(entry.url, real.as_uri())


if __name__ == "__main__":
    unittest.main()
