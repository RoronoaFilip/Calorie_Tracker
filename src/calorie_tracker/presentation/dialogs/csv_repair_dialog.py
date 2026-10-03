"""A popup that shows a whole CSV as an editable table so its problems can be fixed in memory and resubmitted."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from calorie_tracker.infrastructure.csv_issues import CsvIssue
from calorie_tracker.infrastructure.csv_reading import CsvTable
from calorie_tracker.presentation.control_styles import fit_button_text
from calorie_tracker.presentation.dialogs.csv_review_widgets import BAD_TEXT, ERROR_BG, GOOD_TEXT, WARNING_BG

_ROW_HEIGHT = 40
_MIN_COLUMN, _MAX_COLUMN = 90, 300
_EDITOR_STYLE = """
    QTableWidget { background: #f8fafd; alternate-background-color: #f1f5fb; }
    QTableWidget QLineEdit { padding: 2px 8px; min-height: 0; border-radius: 0; border: 2px solid #536fd1;
                             background: #ffffff; }
    QTableWidget::item { padding: 2px 8px; }
"""


def column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA (spreadsheet-style names for the columns)."""
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


class CsvRepairDialog(QDialog):
    """Edit a CSV that failed validation, entirely in memory (the file on disk is never touched).

    ``validate`` re-checks the edited table and returns its remaining issues; it is run as the user types.
    Accepting happens only with a clean table, or after skipping the rows that still have problems.
    Afterwards ``repaired_table`` holds the rows to try again with.
    """

    def __init__(
        self,
        table: CsvTable,
        validate: Callable[[CsvTable], Sequence[CsvIssue]],
        *,
        title: str = "Fix the CSV file",
        intro: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._source = table
        self._validate = validate
        self._skipped_rows: set[int] = set()
        self.issues: tuple[CsvIssue, ...] = ()
        self._mapped_issues: list[CsvIssue] = []  # ``issues`` with rows mapped to table rows
        self._marked_cells: set[tuple[int, int]] = set()
        self._marked_rows: set[int] = set()
        self.setWindowTitle(title)
        self.setMinimumSize(900, 620)
        self.resize(1120, 720)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        heading = QLabel("This file needs a few fixes before it can be imported")
        heading.setObjectName("csvRepairHeading")
        heading.setWordWrap(True)
        heading.setStyleSheet("font-size: 18px; font-weight: 650; color: #172538;")
        layout.addWidget(heading)
        explanation = QLabel(
            (intro + " " if intro else "")
            + "Double-click any cell to edit it — including the column names in the header row. "
            "Changes are made in memory only; your original file is never modified."
        )
        explanation.setObjectName("csvRepairIntro")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        self.status_label = QLabel()
        self.status_label.setObjectName("csvRepairStatus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        panel = QFrame()
        panel.setObjectName("card")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 10, 12, 10)
        panel_layout.setSpacing(6)
        panel_title = QLabel("Problems to fix — select one to jump to it")
        panel_title.setStyleSheet("font-weight: 650;")
        panel_layout.addWidget(panel_title)
        self.issue_list = QListWidget()
        self.issue_list.setObjectName("csvRepairIssues")
        self.issue_list.setAccessibleName("Problems found in the CSV file")
        self.issue_list.setMaximumHeight(124)
        self.issue_list.setWordWrap(True)
        self.issue_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.issue_list.itemClicked.connect(self._jump_to_issue)
        self.issue_list.itemActivated.connect(self._jump_to_issue)
        panel_layout.addWidget(self.issue_list)
        layout.addWidget(panel)

        width = max((len(row) for row in table.rows), default=0)
        self.table = QTableWidget(len(table.rows), width)
        self.table.setObjectName("csvRepairTable")
        self.table.setAccessibleName("Editable contents of the CSV file")
        self.table.setStyleSheet(_EDITOR_STYLE)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setHorizontalHeaderLabels([column_letter(index) for index in range(width)])
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setDefaultSectionSize(_ROW_HEIGHT)
        self.table.verticalHeader().setMinimumWidth(48)
        self.table.horizontalHeader().setMinimumSectionSize(_MIN_COLUMN)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for row_index, row in enumerate(table.rows):
            for column in range(width):
                self.table.setItem(row_index, column, QTableWidgetItem(row[column] if column < len(row) else ""))
        self.table.resizeColumnsToContents()
        for column in range(width):
            self.table.setColumnWidth(
                column, min(_MAX_COLUMN, max(_MIN_COLUMN, self.table.columnWidth(column) + 16))
            )
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.skip_button = QPushButton("Skip problem rows")
        self.skip_button.setObjectName("skipProblemRowsButton")
        self.skip_button.setToolTip("Leave out the rows that still have problems and continue with the rest")
        self.skip_button.clicked.connect(self.skip_problem_rows)
        actions.addWidget(self.skip_button)
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.resubmit_button = QPushButton("Resubmit")
        self.resubmit_button.setObjectName("primaryButton")
        self.resubmit_button.setAccessibleName("Resubmit the corrected data")
        self.resubmit_button.setToolTip("Check the corrected data again and continue when it is valid")
        self.resubmit_button.setDefault(True)
        self.resubmit_button.clicked.connect(self.resubmit)
        actions.addWidget(cancel)
        actions.addWidget(self.resubmit_button)
        layout.addLayout(actions)
        for button in (self.skip_button, cancel, self.resubmit_button):
            fit_button_text(button)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.revalidate)
        self.table.itemChanged.connect(lambda _item: self._timer.start())
        self.revalidate()
        first = next((issue for issue in self.issues if issue.column is not None), None)
        if first is not None:
            self.table.setCurrentCell(first.row, first.column)
            self.table.scrollToItem(self.table.item(first.row, first.column))

    # ---- the data ----------------------------------------------------------------------------------------

    def cell_text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text() if item is not None else ""

    def set_cell(self, row: int, column: int, text: str) -> None:
        """Edit a cell in memory (what typing in the table does) and re-check straight away."""
        item = self.table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, column, item)
        item.setText(text)
        self._timer.stop()
        self.revalidate()

    def current_table(self) -> CsvTable:
        """The table as currently edited, without the rows skipped by the user."""
        rows = [
            [self.cell_text(row, column) for column in range(self.table.columnCount())]
            for row in range(self.table.rowCount())
            if row not in self._skipped_rows
        ]
        return CsvTable(rows, self._source.delimiter, self._source.encoding)

    @property
    def repaired_table(self) -> CsvTable:
        return self.current_table()

    # ---- validation ----------------------------------------------------------------------------------------

    def revalidate(self) -> tuple[CsvIssue, ...]:
        self._timer.stop()
        self.issues = tuple(self._validate(self.current_table()))
        self._show_issues()
        return self.issues

    def _show_issues(self) -> None:
        kept = [row for row in range(self.table.rowCount()) if row not in self._skipped_rows]
        # Issue rows refer to the table that was validated (no skipped rows); map them to table rows.
        issues = [
            CsvIssue(kept[issue.row] if issue.row < len(kept) else issue.row, issue.column, issue.message)
            for issue in self.issues
        ]
        self._mapped_issues = issues
        cell_messages: dict[tuple[int, int], list[str]] = {}
        row_messages: dict[int, list[str]] = {}
        for issue in issues:
            if issue.column is None:
                row_messages.setdefault(issue.row, []).append(issue.message)
            else:
                cell_messages.setdefault((issue.row, issue.column), []).append(issue.message)

        # Only touch cells whose marking changes, so editing stays quick in big files.
        blocker = self.table.blockSignals(True)
        try:
            plain = QFont(self.table.font())
            bold = QFont(plain)
            bold.setBold(True)
            width = self.table.columnCount()
            for row in self._marked_rows | {cell[0] for cell in self._marked_cells}:
                for column in range(width):
                    self._style_cell(row, column, None, plain)
                self.table.setVerticalHeaderItem(row, QTableWidgetItem(str(row + 1)))  # plain row number
            for row in set(row_messages) | {cell[0] for cell in cell_messages}:
                header = QTableWidgetItem(f"⚠ {row + 1}")  # a symbol as well as a colour
                header.setToolTip("; ".join(row_messages.get(row, [])))
                self.table.setVerticalHeaderItem(row, header)
                for column in range(width):
                    messages = cell_messages.get((row, column), []) + row_messages.get(row, [])
                    kind = "cell" if (row, column) in cell_messages else "row"
                    self._style_cell(row, column, (kind, messages), bold if kind == "cell" else plain)
        finally:
            self.table.blockSignals(blocker)
        self._marked_cells = set(cell_messages)
        self._marked_rows = set(row_messages)

        self.issue_list.clear()
        for issue in issues:
            where = (
                f"Row {issue.row + 1}" if issue.column is None
                else f"Row {issue.row + 1}, column {column_letter(issue.column)}"
            )
            entry = QListWidgetItem(f"✕  {where} — {issue.message}")
            entry.setData(Qt.ItemDataRole.UserRole, (issue.row, issue.column))
            entry.setToolTip(issue.message)
            self.issue_list.addItem(entry)

        count = len(issues)
        if count:
            self.status_label.setText(f"✕  {count} problem{'s' if count != 1 else ''} left to fix.")
            self.status_label.setStyleSheet(f"color: {BAD_TEXT}; font-weight: 650;")
        else:
            self.status_label.setText("✓  No problems found. Choose Resubmit to continue.")
            self.status_label.setStyleSheet(f"color: {GOOD_TEXT}; font-weight: 650;")
        self.issue_list.setVisible(count > 0)
        self.skip_button.setEnabled(count > 0 and all(issue.column is not None for issue in issues))

    def _style_cell(self, row: int, column: int, mark: tuple[str, list[str]] | None, font: QFont) -> None:
        item = self.table.item(row, column)
        if item is None:
            return
        item.setFont(font)
        if mark is None:
            item.setData(Qt.ItemDataRole.BackgroundRole, None)
            item.setToolTip("")
            return
        kind, messages = mark
        item.setBackground(ERROR_BG if kind == "cell" else WARNING_BG)
        item.setToolTip("\n".join(messages))

    def _jump_to_issue(self, entry: QListWidgetItem) -> None:
        row, column = entry.data(Qt.ItemDataRole.UserRole)
        target = column if column is not None else 0
        self.table.setCurrentCell(row, target)
        self.table.scrollToItem(self.table.item(row, target), QAbstractItemView.ScrollHint.PositionAtCenter)
        self.table.setFocus()

    # ---- the buttons -------------------------------------------------------------------------------------------

    def resubmit(self) -> None:
        """Re-check the edited data; continue only when nothing is wrong."""
        if self.revalidate():
            first = self._mapped_issues[0]
            self.table.setCurrentCell(first.row, first.column if first.column is not None else 0)
            return
        self.accept()

    def skip_problem_rows(self) -> None:
        """Leave out the rows that still have problems (only possible for bad values, not a missing column)."""
        if not self.skip_button.isEnabled():
            return
        self._skipped_rows.update(issue.row for issue in self._mapped_issues)
        for row in self._skipped_rows:
            self.table.setRowHidden(row, True)
        self.revalidate()
        self.accept()
