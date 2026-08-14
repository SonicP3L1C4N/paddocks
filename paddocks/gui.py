# SPDX-FileCopyrightText: 2026 Gary Bissett <gary.bissett@gmail.com>
#
# SPDX-License-Identifier: MIT

"""A small Qt window for editing the config.

PySide6 is imported here and nowhere else, so the command line keeps working on
a machine that does not have it.

The three lists are the model. Rather than mirroring the config into widgets and
keeping the two in step through drags, renames and deletions, each row carries
the thing it stands for -- a Group object, or an app id -- and the config is
rebuilt by reading the rows back when needed.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QIcon, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from . import apps, desktop, groups
from .layout import ALIGNMENTS, ARRANGEMENTS, Metrics

ROLE = Qt.ItemDataRole.UserRole
MISSING_COLOUR = QColor(200, 60, 60)


def run(config_path: Path) -> int:
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Paddocks")
    # Only claimed once the menu entry exists: without a matching .desktop file
    # the portal rejects the id and Qt logs a warning on every start.
    if desktop.installed_entry() is not None:
        app.setDesktopFileName(desktop.ICON_NAME)
    app.setWindowIcon(paddocks_icon())
    window = Editor(config_path)
    window.show()
    return app.exec()


def paddocks_icon() -> QIcon:
    """The app icon, in whichever variant suits the current colour scheme."""
    icon = QIcon()
    variant = _colour_scheme()
    for size in desktop.SIZES:
        png = desktop.ICON_SOURCE / f"{desktop.ICON_NAME}-{variant}-{size}.png"
        if png.exists():
            icon.addFile(str(png), QSize(size, size))
    svg = desktop.ICON_SOURCE / f"{desktop.ICON_NAME}-{variant}.svg"
    if icon.isNull() and svg.exists():
        icon.addFile(str(svg))
    return icon if not icon.isNull() else QIcon.fromTheme(desktop.ICON_NAME)


def _colour_scheme() -> str:
    """Qt knows the scheme directly; fall back to the palette, then kdeglobals."""
    hints = QGuiApplication.styleHints()
    scheme = hints.colorScheme() if hasattr(hints, "colorScheme") else None
    if scheme == Qt.ColorScheme.Dark:
        return "dark"
    if scheme == Qt.ColorScheme.Light:
        return "light"
    palette = QGuiApplication.palette()
    if palette is not None:
        window = palette.color(QPalette.ColorRole.Window)
        return "dark" if window.lightness() < 128 else "light"
    return desktop.preferred_variant()


def app_icon(entry: apps.Entry | None) -> QIcon:
    """Desktop files name a theme icon, but are also allowed a full path."""
    if entry is None or not entry.icon:
        return QIcon.fromTheme("application-x-executable")
    if "/" in entry.icon:
        return QIcon(entry.icon) if Path(entry.icon).exists() else QIcon()
    return QIcon.fromTheme(entry.icon)


class Worker(QThread):
    """Runs apply/dry-run off the UI thread; it stops plasmashell and waits."""

    done = Signal(bool, str)

    def __init__(self, config: groups.Config, dry_run: bool):
        super().__init__()
        self.config = config
        self.dry_run = dry_run

    def run(self) -> None:
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                # Explicitly not strict, whatever the config says. Strict stops
                # an unresolved id being dropped unnoticed; here the editor has
                # already shown it in red, and refusing to apply would leave no
                # way to rebuild the desktop short of deleting an entry the
                # user may want to keep.
                groups.apply(self.config, dry_run=self.dry_run, strict=False)
        except Exception as exc:  # surfaced in the output dialog
            self.done.emit(False, f"{out.getvalue()}\nerror: {exc}")
            return
        self.done.emit(True, out.getvalue())


class OutputDialog(QDialog):
    def __init__(self, parent, title: str, text: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(700, 420)
        view = QPlainTextEdit(text.strip() or "(no output)")
        view.setReadOnly(True)
        view.setStyleSheet("font-family: monospace;")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        box = QVBoxLayout(self)
        box.addWidget(view)
        box.addWidget(buttons)


class Editor(QMainWindow):
    def __init__(self, config_path: Path):
        super().__init__()
        self.config_path = config_path
        self.index = apps.build()
        self.metrics = Metrics()
        self.arrangement = "row"
        self.dirty = False
        self.worker: Worker | None = None

        self.setWindowTitle("Paddocks")
        self.setWindowIcon(paddocks_icon())
        self.resize(1080, 620)
        self._build()
        self._load()

    # ---------------------------------------------------------------- build

    def _build(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._groups_panel())
        splitter.addWidget(self._contents_panel())
        splitter.addWidget(self._library_panel())
        splitter.setSizes([240, 380, 420])

        root = QVBoxLayout()
        root.addWidget(splitter, 1)
        root.addLayout(self._bottom_bar())

        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready")

    def _groups_panel(self) -> QWidget:
        self.group_list = QListWidget()
        self.group_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        # A drop that overwrites instead of inserting would silently delete the
        # group landed on. False is the default for list views; say so anyway.
        self.group_list.setDragDropOverwriteMode(False)
        self.group_list.currentItemChanged.connect(self._group_changed)
        self.group_list.model().rowsMoved.connect(self._touch)
        self.group_list.itemDoubleClicked.connect(lambda _: self._rename_group())

        add = QPushButton(QIcon.fromTheme("list-add"), "Add")
        add.clicked.connect(self._add_group)
        add_folder = QPushButton(QIcon.fromTheme("folder-open"), "Add folder")
        add_folder.setToolTip("A group that shows a folder's contents, live")
        add_folder.clicked.connect(self._add_folder_group)
        rename = QPushButton(QIcon.fromTheme("edit-rename"), "Rename")
        rename.clicked.connect(self._rename_group)
        delete = QPushButton(QIcon.fromTheme("list-remove"), "Delete")
        delete.clicked.connect(self._delete_group)

        buttons = QHBoxLayout()
        for button in (add, add_folder, rename, delete):
            buttons.addWidget(button)

        return _panel("Groups — drag to reorder", self.group_list, buttons)

    def _contents_panel(self) -> QWidget:
        self.app_list = QListWidget()
        self.app_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.app_list.setDragDropOverwriteMode(False)
        self.app_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.app_list.setIconSize(QSize(24, 24))
        self.app_list.model().rowsMoved.connect(self._touch)
        self.app_list.itemDoubleClicked.connect(lambda _: self._remove_apps())

        self.remove_button = QPushButton(QIcon.fromTheme("list-remove"), "Remove")
        self.remove_button.clicked.connect(self._remove_apps)
        buttons = QHBoxLayout()
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)

        self.contents_label = QLabel("Applications in group")
        return _panel(self.contents_label, self.app_list, buttons)

    def _library_panel(self) -> QWidget:
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search installed applications…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_library)

        self.library = QListWidget()
        self.library.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.library.setIconSize(QSize(24, 24))
        self.library.itemDoubleClicked.connect(lambda _: self._add_apps())

        entries = sorted(self.index.visible(),
                         key=lambda e: (e.name.casefold(), e.app_id))
        # Two packagings of the same app ship the same Name=, so a plain list
        # has several rows reading "Discord" with nothing to choose between
        # them. Only the ambiguous ones get the id spelled out.
        seen: dict[str, int] = {}
        for entry in entries:
            seen[entry.name] = seen.get(entry.name, 0) + 1
        for entry in entries:
            label = entry.name or entry.app_id
            if entry.name and seen[entry.name] > 1:
                label = f"{entry.name}  —  {entry.app_id}"
            item = QListWidgetItem(app_icon(entry), label)
            item.setData(ROLE, entry.app_id)
            item.setToolTip(f"{entry.app_id}\n{entry.path}")
            self.library.addItem(item)

        self.add_app_button = QPushButton(QIcon.fromTheme("go-previous"),
                                          "Add to group")
        self.add_app_button.clicked.connect(self._add_apps)
        buttons = QHBoxLayout()
        buttons.addWidget(self.add_app_button)
        buttons.addStretch(1)

        panel = _panel(f"Installed applications ({self.library.count()})",
                       self.library, buttons)
        panel.layout().insertWidget(1, self.search)
        return panel

    def _bottom_bar(self) -> QHBoxLayout:
        self.arrangement_box = QComboBox()
        self.arrangement_box.addItems(ARRANGEMENTS)
        self.arrangement_box.currentTextChanged.connect(self._touch)

        self.align_box = QComboBox()
        self.align_box.addItems(ALIGNMENTS)
        self.align_box.currentTextChanged.connect(self._touch)

        self.columns_box = QSpinBox()
        self.columns_box.setRange(1, 12)
        self.columns_box.setToolTip(
            "How many icons a group gets across before it wraps to another row")
        self.columns_box.valueChanged.connect(self._touch)

        self.preview_button = QPushButton(QIcon.fromTheme("view-preview"), "Preview")
        self.preview_button.setToolTip("Show the layout without changing anything")
        self.preview_button.clicked.connect(lambda: self._run(dry_run=True))

        self.save_button = QPushButton(QIcon.fromTheme("document-save"), "Save")
        self.save_button.clicked.connect(self._save)

        self.apply_button = QPushButton(QIcon.fromTheme("dialog-ok-apply"),
                                        "Save && Apply")
        self.apply_button.setToolTip("Rebuilds the desktop; restarts plasmashell")
        self.apply_button.clicked.connect(self._save_and_apply)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Arrangement"))
        bar.addWidget(self.arrangement_box)
        bar.addWidget(QLabel("Align"))
        bar.addWidget(self.align_box)
        bar.addWidget(QLabel("Max columns"))
        bar.addWidget(self.columns_box)
        bar.addStretch(1)
        for button in (self.preview_button, self.save_button, self.apply_button):
            bar.addWidget(button)
        return bar

    # ----------------------------------------------------------- load/save

    def _load(self) -> None:
        if not self.config_path.exists():
            self.statusBar().showMessage(
                f"{self.config_path} does not exist yet — add a group to start")
            self._sync_settings()
            return
        try:
            config = groups.load_config(self.config_path)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "Could not read the config", str(exc))
            self.statusBar().showMessage("Config could not be read")
            self._sync_settings()
            return

        self.metrics = config.metrics
        self.arrangement = config.arrangement
        for group in config.groups:
            self._add_group_item(group)
        self._sync_settings()
        if self.group_list.count():
            self.group_list.setCurrentRow(0)
        self.dirty = False
        self._update_title()

        if config.warnings:
            self.statusBar().showMessage("; ".join(config.warnings))
        else:
            self.statusBar().showMessage(f"Loaded {self.config_path}")

    def _sync_settings(self) -> None:
        for box, value in ((self.arrangement_box, self.arrangement),
                           (self.align_box, self.metrics.align)):
            box.blockSignals(True)
            box.setCurrentText(value)
            box.blockSignals(False)
        self.columns_box.blockSignals(True)
        self.columns_box.setValue(self.metrics.max_columns)
        self.columns_box.blockSignals(False)

    def _config(self) -> groups.Config:
        """Read the widgets back into a Config."""
        self._flush_apps()
        self.metrics.align = self.align_box.currentText()
        self.metrics.max_columns = self.columns_box.value()
        ordered = [self.group_list.item(row).data(ROLE)
                   for row in range(self.group_list.count())]
        return groups.Config(groups=ordered, metrics=self.metrics,
                             arrangement=self.arrangement_box.currentText())

    def _save(self) -> bool:
        config = self._config()
        if not config.groups:
            QMessageBox.warning(self, "Nothing to save",
                                "Add at least one group first.")
            return False

        text = groups.dump_config(config, self.index)
        try:
            # Written alongside and renamed, so an interrupted save cannot
            # leave a half-written config behind.
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.config_path.with_suffix(".toml.tmp")
            temp.write_text(text)
            os.replace(temp, self.config_path)
        except OSError as exc:
            QMessageBox.critical(self, "Could not save", str(exc))
            return False

        self.dirty = False
        self._update_title()
        self.statusBar().showMessage(f"Saved {self.config_path}")
        return True

    def _save_and_apply(self) -> None:
        if self._save():
            self._run(dry_run=False)

    def _run(self, dry_run: bool) -> None:
        config = self._config()
        if not config.groups:
            QMessageBox.warning(self, "Nothing to do", "Add at least one group first.")
            return

        self._set_busy(True)
        self.statusBar().showMessage(
            "Working out the layout…" if dry_run
            else "Rebuilding the desktop — plasmashell will restart…")

        self.worker = Worker(config, dry_run)
        self.worker.done.connect(
            lambda ok, text: self._finished(ok, text, dry_run))
        self.worker.start()

    def _finished(self, ok: bool, text: str, dry_run: bool) -> None:
        self._set_busy(False)
        title = "Preview" if dry_run else "Apply"
        OutputDialog(self, title if ok else f"{title} failed", text).exec()
        self.statusBar().showMessage(
            f"{title} finished" if ok else f"{title} failed — see the output")
        self.worker = None

    def _set_busy(self, busy: bool) -> None:
        for button in (self.preview_button, self.save_button, self.apply_button):
            button.setEnabled(not busy)

    # -------------------------------------------------------------- groups

    def _add_group_item(self, group: groups.Group) -> QListWidgetItem:
        icon = "folder-open" if group.is_folder else "folder"
        item = QListWidgetItem(QIcon.fromTheme(icon), group.name)
        if group.is_folder:
            item.setToolTip(f"Folder group, showing {group.expanded_path()}")
        item.setData(ROLE, group)
        self.group_list.addItem(item)
        return item

    def _current_group(self) -> groups.Group | None:
        item = self.group_list.currentItem()
        return item.data(ROLE) if item else None

    def _group_changed(self, current, previous) -> None:
        if previous is not None:
            self._flush_apps(previous.data(ROLE))
        group = current.data(ROLE) if current else None
        self.app_list.clear()

        if group is not None and group.is_folder:
            # A folder group has no app list to edit -- Plasma reads the
            # directory live. Show what it points at instead, and take the
            # editing affordances away rather than letting a drop or a
            # double-click build a list that would be discarded on save.
            self.contents_label.setText(f"“{group.name}” shows a folder")
            target = group.expanded_path()
            item = QListWidgetItem(QIcon.fromTheme("folder-open"), str(target))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            if not target.exists():
                item.setForeground(QBrush(MISSING_COLOUR))
                item.setText(f"{target}  (does not exist yet)")
            self.app_list.addItem(item)
            self._set_app_editing(False)
            return

        self._set_app_editing(True)
        self.contents_label.setText(
            f"Applications in “{group.name}” — drag to reorder" if group
            else "Applications in group")
        if group is None:
            return
        for app_id in group.apps:
            self.app_list.addItem(self._app_item(app_id))

    def _set_app_editing(self, on: bool) -> None:
        self.app_list.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove if on
            else QAbstractItemView.DragDropMode.NoDragDrop)
        self.remove_button.setEnabled(on)
        self.add_app_button.setEnabled(on)

    def _app_item(self, app_id: str) -> QListWidgetItem:
        entry, how = self.index.resolve(app_id)
        if entry is None:
            # Kept rather than dropped, so opening and saving the config never
            # silently loses an id whose application is temporarily missing.
            item = QListWidgetItem(QIcon.fromTheme("dialog-warning"),
                                   f"{app_id}  (not installed)")
            item.setForeground(QBrush(MISSING_COLOUR))
            suggestions = self.index.suggest(app_id)
            tip = "Nothing matches this id."
            if suggestions:
                tip += "\nDid you mean: " + ", ".join(suggestions)
            item.setToolTip(tip)
        else:
            item = QListWidgetItem(app_icon(entry), entry.name or app_id)
            note = f"\nmatched by name, from {app_id}" if how == "alias" else ""
            item.setToolTip(f"{entry.app_id}{note}")
        item.setData(ROLE, app_id)
        return item

    def _add_group(self) -> None:
        name, ok = QInputDialog.getText(self, "New group", "Group name:")
        name = name.strip()
        if not ok or not name:
            return
        if self._name_taken(name):
            QMessageBox.warning(self, "Name in use",
                                f"A group called “{name}” already exists. "
                                "Group names are the widget titles, so they "
                                "have to be unique.")
            return
        item = self._add_group_item(groups.Group(name=name, apps=[]))
        self.group_list.setCurrentItem(item)
        self._touch()

    def _add_folder_group(self) -> None:
        """A group that shows a folder, rather than a list of launchers."""
        chosen = QFileDialog.getExistingDirectory(
            self, "Show which folder?", str(Path.home()))
        if not chosen:
            return
        target = Path(chosen)

        # Offered rather than imposed: the folder's own name is the obvious
        # title, but the group name is the widget's heading and has to be
        # unique, so it is worth a prompt.
        name, ok = QInputDialog.getText(
            self, "New folder group", "Group name:", text=target.name)
        name = name.strip()
        if not ok or not name:
            return
        if self._name_taken(name):
            QMessageBox.warning(self, "Name in use",
                                f"A group called “{name}” already exists.")
            return

        # Stored with ~ intact when it is under home, so the config stays
        # portable between machines and readable to whoever opens it.
        try:
            shown = f"~/{target.relative_to(Path.home())}"
        except ValueError:
            shown = str(target)

        item = self._add_group_item(
            groups.Group(name=name, apps=[], path=shown))
        self.group_list.setCurrentItem(item)
        self._touch()

    def _rename_group(self) -> None:
        item = self.group_list.currentItem()
        if item is None:
            return
        group = item.data(ROLE)
        name, ok = QInputDialog.getText(self, "Rename group", "Group name:",
                                        text=group.name)
        name = name.strip()
        if not ok or not name or name == group.name:
            return
        if self._name_taken(name):
            QMessageBox.warning(self, "Name in use",
                                f"A group called “{name}” already exists.")
            return
        group.name = name
        item.setText(name)
        self.contents_label.setText(f"Applications in “{name}” — drag to reorder")
        self._touch()

    def _delete_group(self) -> None:
        row = self.group_list.currentRow()
        if row < 0:
            return
        group = self.group_list.item(row).data(ROLE)
        confirm = QMessageBox.question(
            self, "Delete group",
            f"Delete “{group.name}” and its {len(group.apps)} application(s) "
            "from the config?")
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.group_list.takeItem(row)
        self._touch()

    def _name_taken(self, name: str) -> bool:
        folded = name.casefold()
        return any(self.group_list.item(row).data(ROLE).name.casefold() == folded
                   for row in range(self.group_list.count()))

    # ---------------------------------------------------------------- apps

    def _flush_apps(self, group: groups.Group | None = None) -> None:
        """Copy the visible app rows back into the group they belong to."""
        group = group if group is not None else self._current_group()
        if group is None:
            return
        if group.is_folder:
            # The rows showing are the folder's path, not app ids. Reading them
            # back would put a directory name into `apps` and lose the path.
            return
        group.apps = [self.app_list.item(row).data(ROLE)
                      for row in range(self.app_list.count())]

    def _add_apps(self) -> None:
        group = self._current_group()
        if group is None:
            self.statusBar().showMessage("Select a group first")
            return
        if group.is_folder:
            self.statusBar().showMessage(
                f"“{group.name}” shows a folder; put the file in the folder "
                "instead")
            return
        present = {self.app_list.item(row).data(ROLE)
                   for row in range(self.app_list.count())}
        added, skipped = 0, 0
        for item in self.library.selectedItems():
            app_id = item.data(ROLE)
            if app_id in present:
                skipped += 1
                continue
            self.app_list.addItem(self._app_item(app_id))
            present.add(app_id)
            added += 1
        if added:
            self._touch()
        message = f"Added {added} to “{group.name}”" if added else "Nothing added"
        self.statusBar().showMessage(
            f"{message}{f' ({skipped} already there)' if skipped else ''}")

    def _remove_apps(self) -> None:
        rows = sorted((self.app_list.row(i) for i in self.app_list.selectedItems()),
                      reverse=True)
        for row in rows:
            self.app_list.takeItem(row)
        if rows:
            self._touch()

    def _filter_library(self, text: str) -> None:
        needle = text.strip().casefold()
        for row in range(self.library.count()):
            item = self.library.item(row)
            hit = (needle in item.text().casefold()
                   or needle in item.data(ROLE).casefold())
            item.setHidden(bool(needle) and not hit)

    # --------------------------------------------------------------- state

    def _touch(self, *_) -> None:
        self.dirty = True
        self._update_title()

    def _update_title(self) -> None:
        star = "*" if self.dirty else ""
        self.setWindowTitle(f"Paddocks — {self.config_path.name}{star}")

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.statusBar().showMessage("Still applying — hold on")
            event.ignore()
            return
        if not self.dirty:
            event.accept()
            return
        answer = QMessageBox.question(
            self, "Unsaved changes", "Save your changes before closing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Cancel:
            event.ignore()
        elif answer == QMessageBox.StandardButton.Discard or self._save():
            event.accept()
        else:
            event.ignore()


def _panel(heading, list_widget: QListWidget, buttons: QHBoxLayout) -> QWidget:
    box = QVBoxLayout()
    box.setContentsMargins(0, 0, 0, 0)
    box.addWidget(heading if isinstance(heading, QLabel) else QLabel(heading))
    box.addWidget(list_widget, 1)
    box.addLayout(buttons)
    panel = QWidget()
    panel.setLayout(box)
    return panel
