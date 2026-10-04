"""Type several foods at once ("Oats 45 breakfast", one per line) and review them before saving."""

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.application.diary import MEALS
from calorie_tracker.application.quick_add import quick_add_rows

EXAMPLE = "Oats 45 breakfast\nEgg 2 breakfast\nChicken breast 150 lunch\nEgg 1/2"


class QuickAddDialog(QDialog):
    """One line per entry: food name, amount (grams, or a count for counted foods) and optionally the meal."""

    def __init__(self, diary_date: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Quick add")
        self.setMinimumSize(620, 460)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        intro = QLabel(
            f"Add several entries to {diary_date} at once. Write one per line: the food, the amount and, "
            "if you like, the meal. The next screen lets you fix anything that was not understood: "
            "choose the right food or the meal."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.text_input = QPlainTextEdit()
        self.text_input.setObjectName("quickAddText")
        self.text_input.setAccessibleName("Entries to add, one per line")
        self.text_input.setPlaceholderText(EXAMPLE)
        layout.addWidget(self.text_input, 1)
        hint = QLabel(
            "Amounts are grams, or a number of items for foods counted per item (½ can be written 1/2 or 0.5). "
            "Ctrl+Enter reviews the entries."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #536175;")
        layout.addWidget(hint)
        meal_row = QHBoxLayout()
        meal_row.addWidget(QLabel("Meal for lines without one"))
        self.default_meal = QComboBox()
        self.default_meal.setAccessibleName("Meal for lines without a meal")
        self.default_meal.addItem("Ask me during review", "")
        for meal in MEALS:
            self.default_meal.addItem(meal, meal)
        meal_row.addWidget(self.default_meal)
        meal_row.addStretch(1)
        layout.addLayout(meal_row)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.review_button = QPushButton("Review entries")
        self.review_button.setObjectName("primaryButton")
        self.review_button.clicked.connect(self._review)
        actions.addWidget(cancel)
        actions.addWidget(self.review_button)
        layout.addLayout(actions)
        for keys in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(keys), self, activated=self._review)
        self.text_input.textChanged.connect(self._update_enabled)
        self._update_enabled()
        self.text_input.setFocus()

    def _update_enabled(self) -> None:
        self.review_button.setEnabled(bool(self.text_input.toPlainText().strip()))

    def _review(self) -> None:
        if self.review_button.isEnabled():
            self.accept()

    def rows(self) -> list[list[str]]:
        """Header plus one [food, amount, meal] row per typed line, ready for the diary CSV checks."""
        return quick_add_rows(self.text_input.toPlainText(), self.default_meal.currentData() or "")
