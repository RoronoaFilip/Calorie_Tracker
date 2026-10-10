"""The one import dialog every import button opens: choose or drop files, or paste CSV text."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.infrastructure.csv_kind import CsvKind
from calorie_tracker.infrastructure.file_kinds import CSV, IMAGE, IMPORT_FILTER, ZIP
from calorie_tracker.presentation.control_styles import fit_button_text
from calorie_tracker.presentation.file_drop import FileDropMixin
from calorie_tracker.presentation.import_help import make_help_button
from calorie_tracker.presentation.paste_highlight import PasteHighlighter

RAW_PROMPT = (
    "Paste CSV text below, starting with its header row. The header tells the app what it is; "
    "add one row per line."
)


class ImportDialog(FileDropMixin, QDialog):
    """Accepts any mix of CSV files, barcode photos and zip files, or pasted CSV text.

    After ``exec()``: ``paths`` holds the chosen or dropped files, or ``pasted_text`` holds the pasted CSV.
    The raw-input box starts empty and shows, as you type, what the text is and where the problems are.
    """

    drop_kinds = frozenset({CSV, IMAGE, ZIP})

    def __init__(self, importers: Mapping[CsvKind, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.paths: list[str] = []
        self.pasted_text: str | None = None
        self.init_file_drop()
        self.setWindowTitle("Import files")
        self.setMinimumWidth(640)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        intro = QLabel(
            "Import foods, diary entries and recipes from CSV files, barcode photos, or zip files that hold them. "
            "Choose or drop as many as you like; each one is checked in a review screen before anything is saved. "
            "Click ? to see every supported format."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.drop_zone = QLabel("⤓  Drag and drop files here (CSV, photos, zip)")
        self.drop_zone.setObjectName("csvDropZone")
        self.drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_zone.setWordWrap(True)
        self.drop_zone.setMinimumHeight(72)
        layout.addWidget(self.drop_zone)

        self.raw_panel = QWidget()
        raw_layout = QVBoxLayout(self.raw_panel)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_title = QLabel(RAW_PROMPT)
        raw_title.setWordWrap(True)
        raw_layout.addWidget(raw_title)
        self.raw_input = QPlainTextEdit()
        self.raw_input.setObjectName("csvRawInput")
        self.raw_input.setAccessibleName("Raw CSV text")
        self.raw_input.setMinimumHeight(170)
        raw_layout.addWidget(self.raw_input)
        self.status_label = QLabel()
        self.status_label.setObjectName("pasteStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("What the pasted text will import")
        raw_layout.addWidget(self.status_label)
        self.raw_panel.setVisible(False)
        layout.addWidget(self.raw_panel)
        self.highlighter = PasteHighlighter(self.raw_input, self.status_label, importers, self)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.help_button = make_help_button(self)
        actions.addWidget(self.help_button)
        self.raw_toggle = QPushButton("Raw input")
        self.raw_toggle.setObjectName("rawInputToggle")
        self.raw_toggle.setCheckable(True)
        self.raw_toggle.setAccessibleName("Switch between choosing files and pasting raw CSV text")
        self.raw_toggle.setToolTip("Paste CSV text instead of choosing files")
        self.raw_toggle.toggled.connect(self._raw_toggled)
        actions.addWidget(self.raw_toggle)
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        self.choose_button = QPushButton("Choose files…")
        self.choose_button.setObjectName("primaryButton")
        self.choose_button.setAccessibleName("Choose files to import")
        self.choose_button.clicked.connect(self._choose_files)
        actions.addWidget(self.choose_button)
        self.use_text_button = QPushButton("Import pasted text")
        self.use_text_button.setObjectName("primaryButton")
        self.use_text_button.setAccessibleName("Import the pasted CSV text")
        self.use_text_button.clicked.connect(self._use_text)
        self.use_text_button.setVisible(False)
        self.use_text_button.setEnabled(False)
        actions.addWidget(self.use_text_button)
        layout.addLayout(actions)
        for button in self.findChildren(QPushButton):
            if button is not self.help_button:
                fit_button_text(button)
        self.raw_input.textChanged.connect(self._text_changed)
        for keys in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(keys), self, activated=self._use_text)

    def _text_changed(self) -> None:
        self.use_text_button.setEnabled(bool(self.raw_input.toPlainText().strip()))

    def _raw_toggled(self, raw: bool) -> None:
        self.raw_panel.setVisible(raw)
        self.drop_zone.setVisible(not raw)
        self.choose_button.setVisible(not raw)
        self.use_text_button.setVisible(raw)
        if raw:
            self.raw_input.setFocus()
            self.raw_input.moveCursor(QTextCursor.MoveOperation.End)

    def _use_text(self) -> None:
        text = self.raw_input.toPlainText()
        if not self.raw_toggle.isChecked() or not text.strip():
            return
        self.pasted_text = text
        self.accept()

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Select files to import", "", IMPORT_FILTER)
        if paths:
            self.paths = list(paths)
            self.accept()

    def handle_dropped_files(self, files: list[tuple[str, str]]) -> None:
        self.paths = [path for path, _kind in files]
        self.accept()
