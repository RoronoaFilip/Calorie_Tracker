"""Pick a food or recipe (and an amount) from the catalogue; used by the diary and the CSV review screens."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.bootstrap import ApplicationServices
from calorie_tracker.domain.nutrition import BASIS_COUNT, BASIS_GRAMS
from calorie_tracker.presentation.amount_input import AmountSpinBox

BASIS_ROLE = Qt.ItemDataRole.UserRole + 1


class AddEntryDialog(QDialog):
    """Search the catalogue and choose one item.

    With ``show_amount`` it also asks how much: grams for weighed foods and recipes, a number of items for
    counted foods (the box switches as soon as such a food is selected). Keyboard: type to search,
    Up/Down choose, Enter confirms, Esc closes.
    """

    def __init__(
        self,
        services: ApplicationServices,
        meal: str,
        parent=None,
        *,
        show_amount: bool = True,
        title: str | None = None,
        heading: str | None = None,
        confirm_text: str = "Add",
    ):
        super().__init__(parent)
        self.services = services
        self.setWindowTitle(title or f"Add to {meal}")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(heading or f"Add food or recipe to {meal}"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search foods and recipes  (↑ ↓ to choose, Enter to confirm)")
        self.search_input.setAccessibleName("Search catalogue for diary entry")
        self.search_input.installEventFilter(self)
        layout.addWidget(self.search_input)
        layout.addWidget(QLabel("Recently used"))
        self.recent_results = QListWidget()
        self.recent_results.setAccessibleName("Recently used foods and recipes")
        self.recent_results.setMaximumHeight(130)
        layout.addWidget(self.recent_results)
        layout.addWidget(QLabel("Matching foods and recipes"))
        self.results = QListWidget()
        self.results.setAccessibleName("Matching foods and recipes")
        layout.addWidget(self.results)
        self.amount_label = QLabel("Amount (g)")
        self.amount_input = AmountSpinBox()
        self.amount_input.setAccessibleName("Diary entry amount")
        self.amount_row = QWidget()
        amount_row = QHBoxLayout(self.amount_row)
        amount_row.setContentsMargins(0, 0, 0, 0)
        amount_row.addWidget(self.amount_label)
        amount_row.addWidget(self.amount_input)
        layout.addWidget(self.amount_row)
        self.amount_row.setVisible(show_amount)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.add_button = QPushButton(confirm_text)
        self.add_button.setObjectName("primaryButton")
        self.add_button.setDefault(True)
        self.add_button.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(self.add_button)
        layout.addLayout(actions)
        self.search_input.textChanged.connect(self.refresh)
        self.recent_results.itemSelectionChanged.connect(self._recent_selected)
        self.results.itemSelectionChanged.connect(self._result_selected)
        self.results.itemDoubleClicked.connect(lambda _: self.accept())
        self.recent_results.itemDoubleClicked.connect(lambda _: self.accept())
        self.refresh()
        self.search_input.setFocus()

    # ---- list content -----------------------------------------------------------------------------------

    def _basis_of(self, item_id: str) -> str:
        food = self.services.foods.get(item_id)
        return food.basis if food is not None else BASIS_GRAMS

    @staticmethod
    def _describe(name: str, kind: str, basis: str) -> str:
        if kind == "recipe":
            return f"{name}  ·  Recipe"
        return f"{name}  ·  Food, per item" if basis == BASIS_COUNT else f"{name}  ·  Food"

    def refresh(self) -> None:
        query = self.search_input.text().strip().casefold()
        self.recent_results.blockSignals(True)
        self.recent_results.clear()
        for item_id, name, kind in self.services.diary_repository.recent_items():
            item = QListWidgetItem(self._describe(name, kind, self._basis_of(item_id)))
            item.setData(Qt.ItemDataRole.UserRole, item_id)
            self.recent_results.addItem(item)
        self.recent_results.blockSignals(False)
        self.results.blockSignals(True)
        self.results.clear()
        rows = [(food.name, "food", food.id, food.basis) for food in self.services.foods.search(query)]
        rows.extend((item.draft.name, "recipe", item.id, BASIS_GRAMS) for item in self.services.recipes.search(query))
        for name, kind, item_id, basis in sorted(rows, key=lambda row: row[0].casefold()):
            entry = QListWidgetItem(self._describe(name, kind, basis))
            entry.setData(Qt.ItemDataRole.UserRole, item_id)
            entry.setData(BASIS_ROLE, basis)
            self.results.addItem(entry)
        if self.results.count():
            self.results.setCurrentRow(0)
        self.results.blockSignals(False)
        self._selection_changed()

    # ---- selection ----------------------------------------------------------------------------------------

    def _recent_selected(self) -> None:
        if self.recent_results.currentItem() is not None:
            self.results.blockSignals(True)
            self.results.clearSelection()
            self.results.setCurrentRow(-1)
            self.results.blockSignals(False)
        self._selection_changed()

    def _result_selected(self) -> None:
        if self.results.currentItem() is not None:
            self.recent_results.blockSignals(True)
            self.recent_results.clearSelection()
            self.recent_results.setCurrentRow(-1)
            self.recent_results.blockSignals(False)
        self._selection_changed()

    def _selection_changed(self) -> None:
        item_id = self.selected_item_id
        self.add_button.setEnabled(item_id is not None)
        if item_id is None:
            return
        basis = self._basis_of(item_id)
        if basis != self.amount_input.basis:
            # Counted foods ask "how many" (default 1), weighed ones ask for grams (default 100 g).
            self.amount_input.set_basis(basis)
            self.amount_label.setText("How many (count)" if basis == BASIS_COUNT else "Amount (g)")

    @property
    def selected_item_id(self) -> str | None:
        item = self.recent_results.currentItem() or self.results.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    @property
    def selected_basis(self) -> str:
        item_id = self.selected_item_id
        return self._basis_of(item_id) if item_id else BASIS_GRAMS

    # ---- keyboard -----------------------------------------------------------------------------------------

    def eventFilter(self, watched, event) -> bool:
        """Up/Down/PageUp/PageDown in the search box move through the matches without leaving it."""
        if watched is self.search_input and event.type() == QEvent.Type.KeyPress:
            step = {
                Qt.Key.Key_Down: 1, Qt.Key.Key_Up: -1, Qt.Key.Key_PageDown: 8, Qt.Key.Key_PageUp: -8,
            }.get(event.key())
            if step is not None and self.results.count():
                row = min(max(self.results.currentRow() + step, 0), self.results.count() - 1)
                self.results.setCurrentRow(row)
                return True
        return super().eventFilter(watched, event)

    def handle_enter(self, _focus: QWidget) -> bool:
        """Enter confirms the chosen item (called by the app-wide Enter handling)."""
        if self.add_button.isEnabled():
            self.accept()
        return True
