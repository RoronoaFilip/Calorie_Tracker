"""Drag-and-drop of CSV files only (the Diary page); see ``file_drop`` for CSV-or-photo targets."""

from __future__ import annotations

from PySide6.QtCore import QMimeData

from calorie_tracker.infrastructure.file_kinds import CSV
from calorie_tracker.presentation.file_drop import FileDropMixin, dropped_files


def csv_paths(mime: QMimeData) -> list[str]:
    """Return the local .csv files carried by a drag (other files are ignored)."""
    return [path for path, _kind in dropped_files(mime, {CSV})]


class CsvDropMixin(FileDropMixin):
    """Mix in before a QWidget base; dropping a .csv calls ``handle_dropped_csv(path)``."""

    drop_kinds = frozenset({CSV})

    def init_csv_drop(self) -> None:
        self.init_file_drop()
