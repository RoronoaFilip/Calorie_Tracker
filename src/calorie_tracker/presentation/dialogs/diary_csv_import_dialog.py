from decimal import Decimal

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.application.diary import DiaryEntryInput, MEALS
from calorie_tracker.bootstrap import ApplicationServices
from calorie_tracker.domain.diary import MealPortion
from calorie_tracker.domain.nutrition import unit_label
from calorie_tracker.infrastructure.diary_csv_importer import DiaryCsvPreview, DiaryCsvRow
from calorie_tracker.presentation.control_styles import fit_button_text
from calorie_tracker.presentation.dialogs.add_entry_dialog import AddEntryDialog
from calorie_tracker.presentation.dialogs.csv_review_widgets import (
    ERROR_BG,
    READY_BG,
    WARNING_BG,
    make_mapping_panel,
    mapping_html,
)
from calorie_tracker.presentation.dialogs.meal_split_dialog import MealSplitDialog, describe_portions
from calorie_tracker.presentation.formatting import format_amount


class MealAssignmentDialog(QDialog):
    """Pick one meal for the whole amount, or open the split dialog to share it between meals."""

    def __init__(
        self,
        row: DiaryCsvRow,
        parent: QWidget | None = None,
        current: tuple[MealPortion, ...] = (),
        unit: str = "g",
        food_name: str | None = None,
    ):
        super().__init__(parent)
        self.row = row
        self.unit = unit
        self.meal: str | None = None
        self.portions: tuple[MealPortion, ...] = ()
        self._current = current
        self._food_name = food_name or row.food_name
        self.setWindowTitle("Choose a meal")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Choose a meal for row {row.source_row}:"))
        layout.addWidget(QLabel(f"{self._food_name} · {row.amount_g:g} {unit}"))
        if current:
            now = QLabel(f"Currently: {describe_portions(current, unit)}")
            now.setStyleSheet("color: #536d95;")
            layout.addWidget(now)
        buttons = QHBoxLayout()
        for meal in MEALS:
            button = QPushButton(meal)
            button.setObjectName(f"assignMeal{meal}")
            button.setAccessibleName(f"Assign row {row.source_row} to {meal}")
            button.clicked.connect(lambda checked=False, selected=meal: self.select_meal(selected))
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.split_button = QPushButton("Split between meals…")
        self.split_button.setObjectName("assignSplit")
        self.split_button.setToolTip("Share this amount between several meals, e.g. 200 g lunch + 300 g dinner")
        self.split_button.clicked.connect(self.open_split)
        layout.addWidget(self.split_button)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

    def select_meal(self, meal: str) -> None:
        self.meal = meal
        self.portions = (MealPortion(meal, self.row.amount_g),)
        self.accept()

    def open_split(self) -> None:
        dialog = MealSplitDialog(self._food_name, self.row.amount_g, self._current, self, self.unit)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.portions:
            return
        self.portions = dialog.portions
        self.meal = dialog.portions[0].meal if len(dialog.portions) == 1 else None
        self.accept()


class DiaryCsvReviewDialog(QDialog):
    """Check every imported (or quick-added) line before anything is saved.

    Each row can be given a meal (or split between meals). A row whose food was not found, or matched several
    foods, can be fixed by choosing the food from the catalogue.
    """

    COLUMNS = ("CSV row", "Food", "Amount", "Meal", "Validation", "", "")
    _MEAL_COLUMN, _FOOD_COLUMN = 5, 6

    def __init__(
        self,
        services: ApplicationServices,
        diary_date: str,
        preview: DiaryCsvPreview,
        parent: QWidget | None = None,
        *,
        quick: bool = False,
    ):
        super().__init__(parent)
        self.services = services
        self.diary_date = diary_date
        self.preview = preview
        self.quick = quick
        self.portions: dict[int, tuple[MealPortion, ...]] = {
            row.source_row: (MealPortion(row.meal, row.amount_g),)
            for row in preview.rows
            if row.is_importable and row.meal is not None
        }
        self.food_choices: dict[int, tuple[str, str, str]] = {}  # CSV row -> (catalogue id, name, basis)
        self.imported_entries = ()
        self._buttons: dict[int, QPushButton] = {}
        self._food_buttons: dict[int, QPushButton] = {}
        self.setWindowTitle("Review quick add" if quick else "Review diary CSV import")
        self.setMinimumSize(1040, 600)
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(20)
        self._fit_timer.timeout.connect(self._fit_rows)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Review entries for {diary_date}. Nothing is saved until you choose Import."))
        if not quick:
            layout.addWidget(make_mapping_panel(mapping_html(
                preview.column_matches, preview.ignored_headers, preview.header_row, preview.delimiter,
                (("food_name", "Food name", True), ("amount_g", "Amount (g)", True), ("meal", "Meal", False)),
            )))
        self.summary_label = QLabel()
        self.summary_label.setObjectName("diaryImportSummary")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        self.only_problems = QCheckBox("Show only rows that need attention")
        self.only_problems.setObjectName("onlyProblemsCheck")
        self.only_problems.toggled.connect(self._apply_filter)
        layout.addWidget(self.only_problems)

        self.table = QTableWidget(len(preview.rows), len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAccessibleName("Diary CSV validation results")
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setMinimumSectionSize(34)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self._MEAL_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self._FOOD_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        header.sectionResized.connect(lambda *_args: self._fit_timer.start())
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(3, 230)
        for index, row in enumerate(preview.rows):
            self._set_item(index, 0, str(row.source_row))
            if self._can_choose_meal(row):
                button = QPushButton("Choose meal")
                button.setObjectName(f"editMealRow{row.source_row}")
                button.setAccessibleName(f"Choose or change meal for CSV row {row.source_row}")
                button.setToolTip("Pick a meal or split this amount between meals. You can change it again at any time.")
                button.clicked.connect(lambda checked=False, entry=row: self.choose_meal(entry))
                fit_button_text(button)
                self._buttons[row.source_row] = button
                self.table.setCellWidget(index, self._MEAL_COLUMN, button)
            else:
                self._set_item(index, self._MEAL_COLUMN, "")
            if self._can_choose_food(row):
                food_button = QPushButton("Choose food…")
                food_button.setObjectName(f"chooseFoodRow{row.source_row}")
                food_button.setAccessibleName(f"Choose the food for CSV row {row.source_row}")
                food_button.setToolTip("Pick the right food from your catalogue for this row")
                food_button.clicked.connect(lambda checked=False, entry=row: self.choose_food(entry))
                fit_button_text(food_button)
                self._food_buttons[row.source_row] = food_button
                self.table.setCellWidget(index, self._FOOD_COLUMN, food_button)
            else:
                self._set_item(index, self._FOOD_COLUMN, "")
        self.table.cellDoubleClicked.connect(self._row_double_clicked)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.all_snacks_button = QPushButton("Put all unassigned rows in Snacks")
        self.all_snacks_button.clicked.connect(self.assign_unassigned_to_snacks)
        actions.addWidget(self.all_snacks_button)
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.import_button = QPushButton()
        self.import_button.setObjectName("primaryButton")
        self.import_button.clicked.connect(self.import_entries)
        actions.addWidget(cancel)
        actions.addWidget(self.import_button)
        layout.addLayout(actions)
        self._refresh_rows()

    # ---- what each row can do ---------------------------------------------------------------------------

    @staticmethod
    def _food_is_the_problem(row: DiaryCsvRow) -> bool:
        """The amount is fine; only the catalogue match failed (not found, or several foods share the name)."""
        return row.amount_g is not None and not row.value_problems and row.catalogue_item_id is None

    def _can_choose_food(self, row: DiaryCsvRow) -> bool:
        return self._food_is_the_problem(row)

    def _can_choose_meal(self, row: DiaryCsvRow) -> bool:
        return row.is_importable or self._food_is_the_problem(row)

    def _food_id(self, row: DiaryCsvRow) -> str | None:
        choice = self.food_choices.get(row.source_row)
        return choice[0] if choice else row.catalogue_item_id

    def _basis(self, row: DiaryCsvRow) -> str:
        choice = self.food_choices.get(row.source_row)
        return choice[2] if choice else row.basis

    def _unit(self, row: DiaryCsvRow) -> str:
        return unit_label(self._basis(row))

    def _is_importable(self, row: DiaryCsvRow) -> bool:
        return row.is_importable or (row.source_row in self.food_choices and self._food_is_the_problem(row))

    @property
    def assigned_meals(self) -> dict[int, str]:
        """Row → meal for rows assigned to a single meal (split rows are in ``portions``)."""
        return {row: parts[0].meal for row, parts in self.portions.items() if len(parts) == 1}

    # ---- table plumbing ------------------------------------------------------------------------------

    def _set_item(self, row_index: int, column: int, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.table.setItem(row_index, column, item)
        return item

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # The table only has its real width once shown; sizing rows before that makes wrapped text tall.
        self._fit_timer.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_timer.start()

    def _fit_rows(self) -> None:
        self.table.resizeRowsToContents()

    def _row_double_clicked(self, row_index: int, _column: int) -> None:
        row = self.preview.rows[row_index]
        if self._is_importable(row):
            self.choose_meal(row)
        elif self._can_choose_food(row):
            self.choose_food(row)

    def choose_meal(self, row: DiaryCsvRow) -> None:
        choice = self.food_choices.get(row.source_row)
        dialog = MealAssignmentDialog(
            row, self, self.portions.get(row.source_row, ()), self._unit(row), choice[1] if choice else None
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.portions:
            return
        self.portions[row.source_row] = dialog.portions
        self._refresh_rows()

    def choose_food(self, row: DiaryCsvRow) -> None:
        """Let the person pick the catalogue food this row means (its typed name was not found or is ambiguous)."""
        dialog = AddEntryDialog(
            self.services, "", self, show_amount=False, title="Choose a food",
            heading=f"Which food is “{row.food_name}” (row {row.source_row})?", confirm_text="Use this food",
        )
        dialog.search_input.setText(row.food_name)
        if not dialog.results.count():
            dialog.search_input.clear()  # nothing contains the typed name: show everything instead
        dialog.search_input.selectAll()
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_item_id is None:
            return
        self.select_food(row, dialog.selected_item_id)

    def select_food(self, row: DiaryCsvRow, item_id: str) -> None:
        food = self.services.foods.get(item_id)
        if food is not None:
            choice = (food.id, food.name, food.basis)
        else:
            recipe = self.services.recipes.get(item_id)
            if recipe is None:
                return
            choice = (recipe.id, recipe.draft.name, "g")
        self.food_choices[row.source_row] = choice
        self._refresh_rows()

    def assign_unassigned_to_snacks(self) -> None:
        for row in self.preview.rows:
            if self._is_importable(row) and row.source_row not in self.portions:
                self.portions[row.source_row] = (MealPortion("Snacks", row.amount_g),)
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        for index, row in enumerate(self.preview.rows):
            choice = self.food_choices.get(row.source_row)
            shown_name = f"{row.food_name} → {choice[1]}" if choice else row.food_name
            self._set_item(index, 1, shown_name)
            self._set_item(index, 2, format_amount(row.amount_g, self._basis(row)) if row.amount_g is not None else "—")
            meal_button = self._buttons.get(row.source_row)
            if not self._is_importable(row):
                if self._can_choose_food(row):
                    status = f"✕ {row.error} Choose the right food with “Choose food…”."
                else:
                    status = f"✕ {row.error}"
                color = ERROR_BG
                self._set_item(index, 3, "—")
                if meal_button is not None:
                    meal_button.setVisible(False)
            else:
                meal_button.setVisible(True)
                parts = self.portions.get(row.source_row)
                if parts is None:
                    status, color = "⚠ Needs a meal — click Choose meal", WARNING_BG
                    self._set_item(index, 3, "—")
                    meal_button.setText("Choose meal")
                else:
                    status = "✓ Ready" if len(parts) == 1 else f"✓ Ready — split into {len(parts)} meals"
                    color = READY_BG
                    self._set_item(index, 3, describe_portions(parts, self._unit(row)))
                    meal_button.setText("Change meal…")
                if choice:
                    status = status.replace("✓ Ready", f"✓ Ready with {choice[1]}", 1)
                fit_button_text(meal_button)
            food_button = self._food_buttons.get(row.source_row)
            if food_button is not None:
                food_button.setText("Change food…" if choice else "Choose food…")
                fit_button_text(food_button)
            self._set_item(index, 4, status)
            for column in range(len(self.COLUMNS)):
                cell = self.table.item(index, column)
                if cell is not None:
                    cell.setBackground(color)
        self._fit_rows()
        self._apply_filter()
        self._refresh_summary()

    def _row_needs_attention(self, row: DiaryCsvRow) -> bool:
        return not self._is_importable(row) or row.source_row not in self.portions

    def _apply_filter(self, *_args) -> None:
        only = self.only_problems.isChecked()
        for index, row in enumerate(self.preview.rows):
            self.table.setRowHidden(index, only and not self._row_needs_attention(row))

    def _refresh_summary(self) -> None:
        importable = [row for row in self.preview.rows if self._is_importable(row)]
        ready_rows = [row for row in importable if row.source_row in self.portions]
        ready = len(ready_rows)
        entries = sum(len(self.portions[row.source_row]) for row in ready_rows)
        skipped = len(self.preview.rows) - len(importable)
        unassigned = sum(row.source_row not in self.portions for row in importable)
        text = f"{ready} row{'s' if ready != 1 else ''} ready to import; {skipped} row{'s' if skipped != 1 else ''} will be skipped."
        if unassigned:
            text += f" Choose a meal for {unassigned} row{'s' if unassigned != 1 else ''}."
        if skipped and any(self._can_choose_food(row) and not self._is_importable(row) for row in self.preview.rows):
            text += " Rows whose food was not found can be fixed with “Choose food…”."
        self.summary_label.setText(text)
        self.import_button.setText(f"Import {entries} entr{'y' if entries == 1 else 'ies'}")
        fit_button_text(self.import_button)
        self.import_button.setEnabled(entries > 0 and unassigned == 0)
        self.all_snacks_button.setEnabled(unassigned > 0)

    def import_entries(self) -> None:
        inputs = tuple(
            DiaryEntryInput(part.meal, self._food_id(row), part.amount_g)
            for row in self.preview.rows
            if self._is_importable(row) and row.source_row in self.portions
            for part in self.portions[row.source_row]
        )
        try:
            self.imported_entries = self.services.diary.add_items_batch(self.diary_date, inputs)
        except Exception as error:
            QMessageBox.critical(self, "Diary import failed", f"No entries were imported.\n\n{error}")
            return
        self.accept()
