"""The ``?`` help page that documents everything the import buttons accept, and the button that opens it."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from calorie_tracker.presentation.control_styles import fit_button_text
from calorie_tracker.presentation.import_formats import HELP_DOCUMENT_STYLE, render_help_html


class ImportHelpDialog(QDialog):
    """Read-only list of every supported CSV structure, photos, zips and the import order."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Import formats")
        self.setMinimumSize(680, 560)
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setObjectName("importHelpText")
        self.browser.setAccessibleName("Supported import formats")
        self.browser.setOpenLinks(False)
        # Set the colours here too, so the page is readable even when Windows is in dark mode.
        self.browser.setStyleSheet(
            "QTextBrowser#importHelpText { background: #f1f5fb; color: #243041; border: 1px solid #c2cede; "
            "border-radius: 7px; padding: 10px; font-size: 16px; }"
        )
        self.browser.document().setDefaultStyleSheet(HELP_DOCUMENT_STYLE)
        self.browser.setHtml(render_help_html())
        layout.addWidget(self.browser, 1)
        actions = QHBoxLayout()
        actions.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("primaryButton")
        close.clicked.connect(self.accept)
        fit_button_text(close)
        actions.addWidget(close)
        layout.addLayout(actions)


def show_import_help(parent: QWidget | None = None) -> None:
    ImportHelpDialog(parent.window() if parent is not None else None).exec()


def make_help_button(parent: QWidget | None = None) -> QPushButton:
    """A ``?`` button that opens the import formats page. Put one beside every import button."""
    button = QPushButton("?", parent)
    button.setObjectName("importHelpButton")
    button.setAccessibleName("Show supported import formats")
    button.setToolTip("Which files can I import? Shows every supported CSV structure.")
    button.setFixedWidth(40)
    button.clicked.connect(lambda checked=False, owner=button: show_import_help(owner))
    return button
