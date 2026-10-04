from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
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

from calorie_tracker.infrastructure.recipe_csv_importer import (
    STATUS_EXISTS,
    STATUS_PROBLEM,
    STATUS_READY,
    RecipeCsvPreview,
)
from calorie_tracker.presentation.control_styles import fit_button_text
from calorie_tracker.presentation.dialogs.csv_review_widgets import (
    ERROR_BG,
    READY_BG,
    SKIPPED_BG,
    make_mapping_panel,
    mapping_html,
)


class RecipeCsvReviewDialog(QDialog):
    """Shows every recipe found in the file and what will happen to it. Nothing is saved until Import."""

    STATUS = {
        STATUS_READY: ("✓ Ready", READY_BG),
        STATUS_EXISTS: ("↷ Skipped", SKIPPED_BG),
        STATUS_PROBLEM: ("✕ Problem", ERROR_BG),
    }
    COLUMNS = ("Recipe", "Ingredients", "CSV rows", "Final yield", "Status")

    def __init__(self, preview: RecipeCsvPreview, parent: QWidget | None = None):
        super().__init__(parent)
        self.preview = preview
        self.setWindowTitle("Review recipe import")
        self.setMinimumSize(900, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Review the recipes below. Nothing is added until you choose Import; "
            "recipes that already exist are never overwritten."
        ))
        layout.addWidget(make_mapping_panel(mapping_html(
            preview.column_matches, preview.ignored_headers, preview.header_row, preview.delimiter,
            (("recipe_name", "Recipe name", True), ("ingredient", "Ingredient", True),
             ("amount", "Amount", True), ("yield_g", "Final yield (g)", False)),
        )))
        ready = len(preview.ready)
        self.summary_label = QLabel(
            f"{len(preview.items)} recipe{'s' if len(preview.items) != 1 else ''} found · {ready} ready · "
            f"{len(preview.items) - ready} will be skipped"
        )
        self.summary_label.setObjectName("recipeImportSummary")
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(len(preview.items), len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAccessibleName("Recipe CSV validation results")
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        for column in range(len(self.COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(len(self.COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 240)
        for index, item in enumerate(preview.items):
            label, color = self.STATUS[item.status]
            rows = f"{item.source_rows[0]}–{item.source_rows[-1]}" if len(item.source_rows) > 1 else str(item.source_rows[0])
            yield_text = f"{item.draft.yield_g:g} g" if item.draft else "—"
            status = f"{label} — {item.message}" if item.message else label
            for column, text in enumerate((item.name or "(no name)", str(item.ingredient_count), rows, yield_text, status)):
                cell = QTableWidgetItem(text)
                cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                cell.setBackground(color)
                self.table.setItem(index, column, cell)
        self.table.resizeRowsToContents()
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.import_button = QPushButton(f"Import {ready} recipe{'s' if ready != 1 else ''}")
        self.import_button.setObjectName("primaryButton")
        self.import_button.setEnabled(ready > 0)
        self.import_button.setDefault(True)
        self.import_button.clicked.connect(self.accept)
        fit_button_text(self.import_button)
        actions.addWidget(cancel)
        actions.addWidget(self.import_button)
        layout.addLayout(actions)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Rows are measured before the table has its real width, which leaves them tall; measure again now.
        QTimer.singleShot(0, self.table.resizeRowsToContents)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.table.resizeRowsToContents()
