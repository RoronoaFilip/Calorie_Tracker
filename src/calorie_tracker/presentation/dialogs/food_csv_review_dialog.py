from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.infrastructure.importer import ImportPreview
from calorie_tracker.presentation.control_styles import fit_button_text
from calorie_tracker.presentation.dialogs.csv_review_widgets import (
    ERROR_BG,
    READY_BG,
    SKIPPED_BG,
    WARNING_BG,
    make_mapping_panel,
    mapping_html,
)


class FoodCsvReviewDialog(QDialog):
    """Shows every row of a food CSV with its status before anything is added to the catalogue."""

    VALUE_COLUMNS = (
        ("calories", "Calories"), ("protein", "Protein"), ("fat", "Fat"),
        ("carbohydrates", "Carbs"), ("fiber", "Fiber"),
    )
    STATUS = {
        "ready": ("✓ Ready", READY_BG),
        "needs_correction": ("✎ Needs correction", WARNING_BG),
        "duplicate": ("↷ Skipped", SKIPPED_BG),
        "excluded": ("⊘ Excluded", SKIPPED_BG),
    }

    def __init__(self, preview: ImportPreview, parent: QWidget | None = None):
        super().__init__(parent)
        self.preview = preview
        self.setWindowTitle("Review food import")
        self.setMinimumSize(960, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Review the foods below. Nothing is added until you choose Import; "
            "existing foods are never overwritten."
        ))
        layout.addWidget(make_mapping_panel(mapping_html(
            preview.column_matches, preview.report.ignored_headers, preview.header_row, preview.delimiter,
            (("food_name", "Food name", True), ("calories", "Calories / 100 g", True),
             ("protein", "Protein / 100 g", True), ("fat", "Fat / 100 g", True),
             ("carbohydrates", "Carbohydrates / 100 g", True), ("fiber", "Fiber / 100 g", False)),
        )))
        report = preview.report
        ready, fix = len(preview.foods), len(preview.invalid_foods)
        self.summary_label = QLabel(
            f"{report.rows_read} rows read · {ready} ready · {fix} need correction · "
            f"{report.duplicate_names} duplicate name{'s' if report.duplicate_names != 1 else ''} skipped · "
            f"{report.excluded_ice_cream_rows} excluded"
        )
        self.summary_label.setObjectName("foodImportSummary")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        self.only_problems = QCheckBox("Show only rows that need attention")
        self.only_problems.setObjectName("onlyProblemsCheck")
        self.only_problems.toggled.connect(self._apply_filter)
        layout.addWidget(self.only_problems)

        headings = ["CSV row", "Food", *(label for _, label in self.VALUE_COLUMNS), "Status"]
        self.table = QTableWidget(len(preview.rows), len(headings))
        self.table.setHorizontalHeaderLabels(headings)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAccessibleName("Food CSV validation results")
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        for column in range(len(headings)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(len(headings) - 1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 210)
        status_column = len(headings) - 1
        for index, review in enumerate(preview.rows):
            label, color = self.STATUS[review.status]
            cells = [str(review.source_row), review.name or "(blank name)"]
            cells += [review.values.get(key, "—") or "—" for key, _ in self.VALUE_COLUMNS]
            cells.append(f"{label} — {review.message}" if review.message else label)
            if review.status == "needs_correction":
                color = ERROR_BG if "not found" in review.message else WARNING_BG
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                item.setBackground(color)
                self.table.setItem(index, column, item)
        self.table.resizeRowsToContents()
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        text = f"Import {ready} food{'s' if ready != 1 else ''}"
        if fix:
            text += f" and correct {fix} row{'s' if fix != 1 else ''}"
        self.import_button = QPushButton(text)
        self.import_button.setObjectName("primaryButton")
        self.import_button.setEnabled(ready > 0 or fix > 0)
        self.import_button.clicked.connect(self.accept)
        fit_button_text(self.import_button)
        actions.addWidget(cancel)
        actions.addWidget(self.import_button)
        layout.addLayout(actions)

    def _apply_filter(self, checked: bool) -> None:
        for index, review in enumerate(self.preview.rows):
            self.table.setRowHidden(index, checked and review.status == "ready")
