from PySide6.QtCore import Qt
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
from calorie_tracker.infrastructure.diary_csv_importer import DiaryCsvPreview, DiaryCsvRow
from calorie_tracker.presentation.control_styles import fit_button_text
from calorie_tracker.presentation.dialogs.csv_review_widgets import (
    ERROR_BG,
    READY_BG,
    WARNING_BG,
    make_mapping_panel,
    mapping_html,
)
from calorie_tracker.presentation.dialogs.meal_split_dialog import MealSplitDialog, describe_portions


class MealAssignmentDialog(QDialog):
    """Pick one meal for the whole amount, or open the split dialog to share it between meals."""

    def __init__(
        self,
        row: DiaryCsvRow,
        parent: QWidget | None = None,
        current: tuple[MealPortion, ...] = (),
    ):
        super().__init__(parent)
        self.row = row
        self.meal: str | None = None
        self.portions: tuple[MealPortion, ...] = ()
        self._current = current
        self.setWindowTitle("Choose a meal")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Choose a meal for row {row.source_row}:"))
        layout.addWidget(QLabel(f"{row.food_name} · {row.amount_g:g} g"))
        if current:
            now = QLabel(f"Currently: {describe_portions(current)}")
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
        dialog = MealSplitDialog(self.row.food_name, self.row.amount_g, self._current, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.portions:
            return
        self.portions = dialog.portions
        self.meal = dialog.portions[0].meal if len(dialog.portions) == 1 else None
        self.accept()


class DiaryCsvReviewDialog(QDialog):
    COLUMNS = ("CSV row", "Food", "Amount", "Meal", "Validation", "")

    def __init__(
        self,
        services: ApplicationServices,
        diary_date: str,
        preview: DiaryCsvPreview,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.services = services
        self.diary_date = diary_date
        self.preview = preview
        self.portions: dict[int, tuple[MealPortion, ...]] = {
            row.source_row: (MealPortion(row.meal, row.amount_g),)
            for row in preview.rows
            if row.is_importable and row.meal is not None
        }
        self.imported_entries = ()
        self._buttons: dict[int, QPushButton] = {}
        self.setWindowTitle("Review diary CSV import")
        self.setMinimumSize(940, 580)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Review entries for {diary_date}. Nothing is saved until you choose Import."))
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
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(1, 200)
        self.table.setColumnWidth(3, 230)
        for index, row in enumerate(preview.rows):
            self._set_item(index, 0, str(row.source_row))
            self._set_item(index, 1, row.food_name)
            self._set_item(index, 2, f"{row.amount_g:g} g" if row.amount_g is not None else "—")
            if row.is_importable:
                button = QPushButton("Choose meal")
                button.setObjectName(f"editMealRow{row.source_row}")
                button.setAccessibleName(f"Choose or change meal for CSV row {row.source_row}")
                button.setToolTip("Pick a meal or split this amount between meals. You can change it again at any time.")
                button.clicked.connect(lambda checked=False, entry=row: self.choose_meal(entry))
                fit_button_text(button)
                self._buttons[row.source_row] = button
                self.table.setCellWidget(index, 5, button)
            else:
                self._set_item(index, 5, "")
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

    @property
    def assigned_meals(self) -> dict[int, str]:
        """Row → meal for rows assigned to a single meal (split rows are in ``portions``)."""
        return {row: parts[0].meal for row, parts in self.portions.items() if len(parts) == 1}

    def _set_item(self, row_index: int, column: int, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.table.setItem(row_index, column, item)
        return item

    def _row_double_clicked(self, row_index: int, _column: int) -> None:
        row = self.preview.rows[row_index]
        if row.is_importable:
            self.choose_meal(row)

    def choose_meal(self, row: DiaryCsvRow) -> None:
        dialog = MealAssignmentDialog(row, self, self.portions.get(row.source_row, ()))
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.portions:
            return
        self.portions[row.source_row] = dialog.portions
        self._refresh_rows()

    def assign_unassigned_to_snacks(self) -> None:
        for row in self.preview.rows:
            if row.is_importable and row.source_row not in self.portions:
                self.portions[row.source_row] = (MealPortion("Snacks", row.amount_g),)
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        for index, row in enumerate(self.preview.rows):
            if not row.is_importable:
                status, color = f"✕ {row.error}", ERROR_BG
                self._set_item(index, 3, "—")
            else:
                parts = self.portions.get(row.source_row)
                if parts is None:
                    status, color = "⚠ Needs a meal — click Choose meal", WARNING_BG
                    self._set_item(index, 3, "—")
                    self._buttons[row.source_row].setText("Choose meal")
                else:
                    status = "✓ Ready" if len(parts) == 1 else f"✓ Ready — split into {len(parts)} meals"
                    color = READY_BG
                    self._set_item(index, 3, describe_portions(parts))
                    self._buttons[row.source_row].setText("Change meal…")
                fit_button_text(self._buttons[row.source_row])
            self._set_item(index, 4, status)
            for column in range(len(self.COLUMNS)):
                cell = self.table.item(index, column)
                if cell is not None:
                    cell.setBackground(color)
        self.table.resizeRowsToContents()
        self._apply_filter()
        self._refresh_summary()

    def _row_needs_attention(self, row: DiaryCsvRow) -> bool:
        return not row.is_importable or row.source_row not in self.portions

    def _apply_filter(self, *_args) -> None:
        only = self.only_problems.isChecked()
        for index, row in enumerate(self.preview.rows):
            self.table.setRowHidden(index, only and not self._row_needs_attention(row))

    def _refresh_summary(self) -> None:
        ready_rows = [row for row in self.preview.rows if row.is_importable and row.source_row in self.portions]
        ready = len(ready_rows)
        entries = sum(len(self.portions[row.source_row]) for row in ready_rows)
        skipped = len(self.preview.skipped_rows)
        unassigned = sum(
            row.is_importable and row.source_row not in self.portions for row in self.preview.rows
        )
        text = f"{ready} row{'s' if ready != 1 else ''} ready to import; {skipped} row{'s' if skipped != 1 else ''} will be skipped."
        if unassigned:
            text += f" Choose a meal for {unassigned} row{'s' if unassigned != 1 else ''}."
        self.summary_label.setText(text)
        self.import_button.setText(f"Import {entries} entr{'y' if entries == 1 else 'ies'}")
        fit_button_text(self.import_button)
        self.import_button.setEnabled(entries > 0 and unassigned == 0)
        self.all_snacks_button.setEnabled(unassigned > 0)

    def import_entries(self) -> None:
        inputs = tuple(
            DiaryEntryInput(part.meal, row.catalogue_item_id, part.amount_g)
            for row in self.preview.rows
            if row.is_importable and row.source_row in self.portions
            for part in self.portions[row.source_row]
        )
        try:
            self.imported_entries = self.services.diary.add_items_batch(self.diary_date, inputs)
        except Exception as error:
            QMessageBox.critical(self, "Diary import failed", f"No entries were imported.\n\n{error}")
            return
        self.accept()
