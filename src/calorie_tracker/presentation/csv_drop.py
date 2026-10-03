"""Drag-and-drop support for opening CSV files from the file manager."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QTimer, Qt


def csv_paths(mime: QMimeData) -> list[str]:
    """Return the local .csv files carried by a drag (other files are ignored)."""
    if not mime.hasUrls():
        return []
    paths = [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
    return [path for path in paths if Path(path).suffix.casefold() == ".csv"]


class CsvDropMixin:
    """Mix in before a QWidget base; dropping a .csv calls ``handle_dropped_csv(path)``."""

    def init_csv_drop(self) -> None:
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def _set_drop_active(self, active: bool) -> None:
        if bool(self.property("dropActive")) == active:
            return
        self.setProperty("dropActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event) -> None:
        if csv_paths(event.mimeData()):
            event.acceptProposedAction()
            self._set_drop_active(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if csv_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._set_drop_active(False)
        event.accept()

    def dropEvent(self, event) -> None:
        paths = csv_paths(event.mimeData())
        self._set_drop_active(False)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        # Run after the drag finishes so the file manager is not frozen behind a modal dialog.
        QTimer.singleShot(0, lambda path=paths[0]: self.handle_dropped_csv(path))

    def handle_dropped_csv(self, path: str) -> None:  # pragma: no cover - overridden
        raise NotImplementedError
