"""Quick add: a table where each row is a food, an amount and a meal. Nothing is typed as CSV."""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.application.diary import MEALS
from calorie_tracker.application.quick_add import quick_add_rows
from calorie_tracker.domain.nutrition import BASIS_COUNT, BASIS_GRAMS
from calorie_tracker.bootstrap import ApplicationServices
from calorie_tracker.presentation.amount_input import AmountSpinBox

_ROW_HEIGHT = 50
_START_ROWS = 3
_FOOD, _AMOUNT, _MEAL, _REMOVE = range(4)


def _meal_for_now() -> str:
    hour = datetime.now().hour
    return MEALS[0] if hour < 11 else MEALS[1] if hour < 16 else MEALS[2] if hour < 21 else MEALS[3]


class QuickAddDialog(QDialog):
    """Add several entries at once.

    Each row has a food (type to search all foods and recipes; any part of the name matches), an amount (grams,
    or a number of items for foods counted per item) and a meal. The rows are turned into a diary CSV table in
    code (``rows()``) and go through the normal CSV review. Keyboard: Enter moves food → amount → next row,
    Ctrl+Enter reviews, Esc closes.
    """

    def __init__(self, services: ApplicationServices, diary_date: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Quick add")
        self.setMinimumSize(780, 480)
        self.resize(860, 560)
        self._names: list[str] = []
        self._basis_by_name: dict[str, str] = {}
        for food in services.foods.search():
            self._add_name(food.name, food.basis)
        for recipe in services.recipes.search():
            self._add_name(recipe.draft.name, BASIS_GRAMS)
        self._names.sort(key=str.casefold)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        intro = QLabel(
            f"Add several entries to {diary_date} at once. Pick the food (type to search), the amount and the meal "
            "for each row. The next screen lets you check everything before it is saved."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("quickAddTable")
        self.table.setAccessibleName("Entries to add")
        self.table.setHorizontalHeaderLabels(["Food or recipe", "Amount", "Meal", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header = self.table.horizontalHeader()
        header.setMinimumHeight(36)
        header.setSectionResizeMode(_FOOD, QHeaderView.ResizeMode.Stretch)
        for column, width in ((_AMOUNT, 170), (_MEAL, 170), (_REMOVE, 116)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)

        self.hint = QLabel(
            "Amounts are grams, or a number of items for foods counted per item (halves are fine)."
        )
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #536175;")
        layout.addWidget(self.hint)

        actions = QHBoxLayout()
        self.add_row_button = QPushButton("+ Add row")
        self.add_row_button.setToolTip("Add a row (Ctrl++)")
        self.add_row_button.setObjectName("quickAddRowButton")
        self.add_row_button.setAutoDefault(False)
        self.add_row_button.clicked.connect(lambda: self.add_row(focus=True))
        actions.addWidget(self.add_row_button)
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        self.review_button = QPushButton("Review entries")
        self.review_button.setObjectName("primaryButton")
        self.review_button.setAutoDefault(False)
        self.review_button.clicked.connect(self._review)
        actions.addWidget(cancel)
        actions.addWidget(self.review_button)
        layout.addLayout(actions)
        for keys in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(keys), self, activated=self._review)
        # Ctrl and "+" (on most keyboards "+" is Shift and "=", so Ctrl+= works too) add a row.
        for keys in ("Ctrl++", "Ctrl+=", "Ctrl+Shift+="):
            QShortcut(QKeySequence(keys), self, activated=lambda: self.add_row(focus=True))

        for _ in range(_START_ROWS):
            self.add_row()
        self._update_enabled()
        self.food_combo(0).setFocus()

    def _add_name(self, name: str, basis: str) -> None:
        key = name.strip().casefold()
        if key not in self._basis_by_name:
            self._names.append(name)
            self._basis_by_name[key] = basis

    # ---- rows -----------------------------------------------------------------------------------------

    def row_count(self) -> int:
        return self.table.rowCount()

    def food_combo(self, row: int) -> QComboBox:
        return self.table.cellWidget(row, _FOOD)

    def amount_input(self, row: int) -> AmountSpinBox:
        return self.table.cellWidget(row, _AMOUNT)

    def meal_combo(self, row: int) -> QComboBox:
        return self.table.cellWidget(row, _MEAL)

    def add_row(self, focus: bool = False) -> int:
        row = self.table.rowCount()
        previous_meal = self.meal_combo(row - 1).currentText() if row else _meal_for_now()
        self.table.insertRow(row)
        self.table.setRowHeight(row, _ROW_HEIGHT)

        food = QComboBox()
        food.setObjectName(f"quickFood{row}")
        food.setAccessibleName(f"Food for row {row + 1}")
        food.setEditable(True)
        food.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        food.addItems(self._names)
        food.setCurrentIndex(-1)
        food.lineEdit().setPlaceholderText("Type to search…")
        completer = food.completer()
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setMaxVisibleItems(10)
        food.lineEdit().textChanged.connect(lambda _text, box=food: self._food_changed(box))
        self.table.setCellWidget(row, _FOOD, food)

        amount = AmountSpinBox()
        amount.setObjectName(f"quickAmount{row}")
        amount.setAccessibleName(f"Amount for row {row + 1}")
        amount.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.table.setCellWidget(row, _AMOUNT, amount)

        meal = QComboBox()
        meal.setObjectName(f"quickMeal{row}")
        meal.setAccessibleName(f"Meal for row {row + 1}")
        meal.addItems(MEALS)
        meal.setCurrentText(previous_meal)
        self.table.setCellWidget(row, _MEAL, meal)

        remove = QPushButton("Remove")
        remove.setObjectName("recipeRemoveButton")
        remove.setAccessibleName(f"Remove row {row + 1}")
        remove.setAutoDefault(False)
        remove.clicked.connect(lambda checked=False, box=food: self._remove_row_of(box))
        self.table.setCellWidget(row, _REMOVE, remove)
        self._update_enabled()
        if focus:
            self.table.scrollToBottom()
            food.setFocus()
        return row

    def _row_of(self, box: QComboBox) -> int:
        return next((row for row in range(self.table.rowCount()) if self.food_combo(row) is box), -1)

    def _remove_row_of(self, box: QComboBox) -> None:
        row = self._row_of(box)
        if row < 0:
            return
        self.table.removeRow(row)
        if self.table.rowCount() == 0:
            self.add_row()
        self._update_enabled()

    def _food_changed(self, box: QComboBox) -> None:
        """Choosing a counted food switches the amount to a number of items; others use grams."""
        row = self._row_of(box)
        if row < 0:
            return
        basis = self._basis_by_name.get(box.currentText().strip().casefold())
        amount = self.amount_input(row)
        if basis is not None and basis != amount.basis:
            amount.set_basis(basis)
        self._update_enabled()

    def _update_enabled(self) -> None:
        if hasattr(self, "review_button"):
            self.review_button.setEnabled(bool(self.entries()))

    # ---- result ---------------------------------------------------------------------------------------

    def entries(self) -> list[tuple[str, str, str]]:
        """(food text, amount, meal) for every row that has a food."""
        result = []
        for row in range(self.table.rowCount()):
            name = self.food_combo(row).currentText().strip()
            if name:
                result.append((name, str(self.amount_input(row).value()), self.meal_combo(row).currentText()))
        return result

    def rows(self) -> list[list[str]]:
        """Header plus one [food_name, amount, meal] row per filled-in table row, ready for the diary CSV checks."""
        return quick_add_rows(self.entries())

    # ---- keyboard -------------------------------------------------------------------------------------

    def handle_enter(self, focus: QWidget) -> bool:
        """Enter moves food → amount → next row's food (adding a row after the last one)."""
        for row in range(self.table.rowCount()):
            food, amount = self.food_combo(row), self.amount_input(row)
            if focus in (food, food.lineEdit()):
                amount.setFocus()
                return True
            if focus in (amount, amount.lineEdit()):
                if row + 1 >= self.table.rowCount():
                    if self.entries():
                        self.add_row(focus=True)
                else:
                    self.food_combo(row + 1).setFocus()
                return True
        return True

    def _review(self) -> None:
        if self.review_button.isEnabled():
            self.accept()
