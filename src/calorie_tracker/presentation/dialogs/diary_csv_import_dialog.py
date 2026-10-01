from calorie_tracker.application.diary import DiaryEntryInput, MEALS
from calorie_tracker.bootstrap import ApplicationServices
from calorie_tracker.infrastructure.diary_csv_importer import DiaryCsvPreview, DiaryCsvRow
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class MealAssignmentDialog(QDialog):
    def __init__(self, row: DiaryCsvRow, parent: QWidget | None = None):
        super().__init__(parent)
        self.meal: str | None = None
        self.setWindowTitle("Choose a meal")
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Choose a meal for row {row.source_row}:"))
        layout.addWidget(QLabel(f"{row.food_name} · {row.amount_g:g} g"))
        buttons = QHBoxLayout()
        for meal in MEALS:
            button = QPushButton(meal)
            button.setObjectName(f"assignMeal{meal}")
            button.setAccessibleName(f"Assign row {row.source_row} to {meal}")
            button.clicked.connect(lambda checked=False, selected=meal: self.select_meal(selected))
            buttons.addWidget(button)
        layout.addLayout(buttons)
        cancel = QPushButton("Cancel import")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

    def select_meal(self, meal: str) -> None:
        self.meal = meal
        self.accept()


class DiaryCsvReviewDialog(QDialog):
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
        self.assigned_meals = {
            row.source_row: row.meal
            for row in preview.rows
            if row.is_importable and row.meal is not None
        }
        self.imported_entries = ()
        self.setWindowTitle("Review diary CSV import")
        self.setMinimumSize(780, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Review entries for {diary_date}. Nothing is saved until you choose Import."))
        self.summary_label = QLabel()
        self.summary_label.setObjectName("diaryImportSummary")
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(len(preview.rows), 5)
        self.table.setHorizontalHeaderLabels(("CSV row", "Food", "Amount", "Meal", "Validation"))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAccessibleName("Diary CSV validation results")
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 210)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 140)
        for index, row in enumerate(preview.rows):
            self._set_item(index, 0, str(row.source_row))
            self._set_item(index, 1, row.food_name)
            self._set_item(index, 2, f"{row.amount_g:g} g" if row.amount_g is not None else "—")
            status = row.error or ("Needs meal" if row.meal is None else "Ready")
            self._set_item(index, 4, status)
            if row.is_importable and row.meal is None:
                self._set_meal_button(index, row, "Choose meal")
            else:
                self._set_item(index, 3, row.meal or "—")
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
        self._refresh_summary()

    def _set_item(self, row_index: int, column: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.table.setItem(row_index, column, item)

    def _set_meal_button(self, row_index: int, row: DiaryCsvRow, label: str) -> None:
        button = QPushButton(label)
        button.setAccessibleName(f"Choose meal for CSV row {row.source_row}")
        button.clicked.connect(lambda checked=False, entry=row: self.choose_meal(entry))
        self.table.setCellWidget(row_index, 3, button)

    def choose_meal(self, row: DiaryCsvRow) -> None:
        dialog = MealAssignmentDialog(row, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.meal is None:
            return
        self.assigned_meals[row.source_row] = dialog.meal
        self._refresh_rows()

    def assign_unassigned_to_snacks(self) -> None:
        for row in self.preview.needs_meal_assignment:
            self.assigned_meals[row.source_row] = "Snacks"
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        for index, row in enumerate(self.preview.rows):
            if not row.is_importable:
                continue
            meal = self.assigned_meals.get(row.source_row)
            if meal is None:
                self._set_meal_button(index, row, "Choose meal")
                self._set_item(index, 4, "Needs meal")
            else:
                self.table.removeCellWidget(index, 3)
                self._set_item(index, 3, meal)
                self._set_item(index, 4, "Ready")
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        ready = sum(
            row.is_importable and self.assigned_meals.get(row.source_row) is not None
            for row in self.preview.rows
        )
        skipped = len(self.preview.skipped_rows)
        unassigned = sum(
            row.is_importable and self.assigned_meals.get(row.source_row) is None
            for row in self.preview.rows
        )
        text = f"{ready} row{'s' if ready != 1 else ''} ready to import; {skipped} row{'s' if skipped != 1 else ''} will be skipped."
        if unassigned:
            text += f" Choose a meal for {unassigned} row{'s' if unassigned != 1 else ''}."
        self.summary_label.setText(text)
        self.import_button.setText(f"Import {ready} entr{'y' if ready == 1 else 'ies'}")
        self.import_button.setEnabled(ready > 0 and unassigned == 0)
        self.all_snacks_button.setEnabled(unassigned > 0)

    def import_entries(self) -> None:
        inputs = tuple(
            DiaryEntryInput(
                self.assigned_meals[row.source_row], row.catalogue_item_id, row.amount_g
            )
            for row in self.preview.rows
            if row.is_importable and self.assigned_meals.get(row.source_row) is not None
        )
        try:
            self.imported_entries = self.services.diary.add_items_batch(self.diary_date, inputs)
        except Exception as error:
            QMessageBox.critical(self, "Diary import failed", f"No entries were imported.\n\n{error}")
            return
        self.accept()
