"""Shared 'read → repair if needed → preview' flow for the food and diary CSV imports."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

from calorie_tracker.infrastructure.csv_reading import CsvTable
from calorie_tracker.presentation.dialogs.csv_repair_dialog import CsvRepairDialog


def preview_with_repair(
    parent: QWidget, table: CsvTable, importer: Any, *, error_title: str, intro: str
) -> Any | None:
    """Return ``importer.preview_table`` of the table, letting the user fix it in memory first if needed.

    ``importer`` needs ``issues_for(table)`` and ``preview_table(table)`` (both CSV importers have them).
    Returns None when the user cancels or the file cannot be used at all.
    """
    if not any(any(cell.strip() for cell in row) for row in table.rows):
        QMessageBox.critical(parent, error_title, "This CSV file is empty.")
        return None
    if importer.issues_for(table):
        dialog = CsvRepairDialog(table, importer.issues_for, title=error_title, intro=intro, parent=parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        table = dialog.repaired_table
    try:
        return importer.preview_table(table)
    except ValueError as error:  # still unusable, e.g. the dialog was accepted without fixing the headers
        QMessageBox.critical(parent, error_title, str(error))
        return None
