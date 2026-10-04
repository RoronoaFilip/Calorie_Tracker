"""A popup that explains the keyboard shortcuts of the app."""

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

# (section title, ((keys, what it does), ...)). "Ctrl" is shown as Cmd on macOS.
SHORTCUT_GROUPS = (
    ("Everywhere", (
        ("F1", "Show this list of keyboard shortcuts"),
        ("Ctrl+1", "Go to Diary"),
        ("Ctrl+2", "Go to Calendar"),
        ("Ctrl+3", "Go to Foods & recipes"),
        ("Ctrl+4", "Go to Settings"),
        ("Esc", "Close the current pop-up"),
        ("Ctrl+W", "Close the current pop-up"),
        ("Enter", "Save or confirm in a pop-up (save a food or recipe, add the chosen item)"),
    )),
    ("Diary", (
        ("Alt+Left", "Previous day"),
        ("Alt+Right", "Next day"),
        ("Ctrl+T", "Jump to today"),
        ("Alt+1", "Add food to Breakfast"),
        ("Alt+2", "Add food to Lunch"),
        ("Alt+3", "Add food to Dinner"),
        ("Alt+4", "Add food to Snacks"),
        ("Ctrl+Shift+A", "Quick add several entries at once"),
        ("Enter", "Save the amount while editing an entry"),
    )),
    ("Add food to a meal", (
        ("Type", "Search foods and recipes"),
        ("Up / Down", "Choose a match without leaving the search box"),
        ("Enter", "Add the chosen item"),
    )),
    ("Quick add", (
        ("Type", "Search all foods and recipes in a row; any part of the name matches"),
        ("Enter", "Move from food to amount to the next row (a new row is added after the last)"),
    )),
    ("Foods & recipes", (
        ("Ctrl+F", "Search (the search box is also focused when you open the page)"),
        ("Ctrl+N", "Add a food"),
        ("Ctrl+Shift+N", "Create a recipe"),
        ("Down", "Move from the search box into the list"),
        ("Enter", "Edit the selected food or recipe"),
        ("Delete", "Archive the selected food or recipe"),
    )),
    ("Recipe editor", (
        ("Type", "Search ingredients; any part of the name matches"),
        ("Enter", "Add the ingredient (in the ingredient row) or save the recipe (anywhere else)"),
        ("Enter", "After changing an amount in the table, go back to the ingredient row"),
    )),
)

_NOTE = (
    "On macOS, Ctrl is the Cmd key. Clicking or tabbing into a field selects its text, "
    "so typing replaces it."
)


def display_keys(keys: str) -> str:
    """'Ctrl+F' as the platform writes it (Cmd+F on macOS); plain words such as 'Type' are left alone."""
    parts = [part.strip() for part in keys.split("/")]
    shown = []
    for part in parts:
        sequence = QKeySequence(part)
        shown.append(sequence.toString(QKeySequence.SequenceFormat.NativeText) if not sequence.isEmpty() else part)
    return " / ".join(shown)


def shortcuts_html() -> str:
    rows = []
    for title, entries in SHORTCUT_GROUPS:
        rows.append(f"<h3 style='margin: 14px 0 4px 0;'>{escape(title)}</h3>")
        rows.append("<table cellspacing='0' cellpadding='4'>")
        for keys, action in entries:
            rows.append(
                f"<tr><td width='170'><b>{escape(display_keys(keys))}</b></td><td>{escape(action)}</td></tr>"
            )
        rows.append("</table>")
    return "".join(rows)


class ShortcutsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self.resize(720, 640)
        layout = QVBoxLayout(self)
        intro = QLabel("Everything you can do from the keyboard.")
        intro.setStyleSheet("font-size: 18px; font-weight: 650;")
        layout.addWidget(intro)
        body = QLabel(shortcuts_html())
        body.setObjectName("shortcutsText")
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        scroll.setAccessibleName("Keyboard shortcuts")
        layout.addWidget(scroll, 1)
        note = QLabel(_NOTE)
        note.setWordWrap(True)
        note.setStyleSheet("color: #536175;")
        layout.addWidget(note)
        actions = QHBoxLayout()
        actions.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("primaryButton")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        layout.addLayout(actions)
        close.setFocus()
