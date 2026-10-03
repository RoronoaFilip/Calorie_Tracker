"""Drag-and-drop support for opening CSV files and photos from the file manager."""

from __future__ import annotations

from collections.abc import Collection

from PySide6.QtCore import QMimeData, QTimer, Qt

from calorie_tracker.infrastructure.file_kinds import CSV, IMAGE, classify_file


def dropped_files(mime: QMimeData, accepted: Collection[str]) -> list[tuple[str, str]]:
    """Return ``(path, kind)`` for each local file in a drag whose kind (csv/image) is in ``accepted``."""
    if not mime.hasUrls():
        return []
    files = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        path = url.toLocalFile()
        kind = classify_file(path)
        if kind in accepted:
            files.append((path, kind))
    return files


class FileDropMixin:
    """Mix in before a QWidget base. Set ``drop_kinds`` to the kinds the widget takes (csv and/or image).

    A dropped CSV calls ``handle_dropped_csv(path)`` and a dropped photo ``handle_dropped_image(path)``.
    The file's content decides which it is, so photos without (or with the wrong) extension still work.
    """

    drop_kinds: frozenset[str] = frozenset({CSV})

    def init_file_drop(self) -> None:
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def _set_drop_active(self, active: bool) -> None:
        if bool(self.property("dropActive")) == active:
            return
        self.setProperty("dropActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event) -> None:
        if dropped_files(event.mimeData(), self.drop_kinds):
            event.acceptProposedAction()
            self._set_drop_active(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if dropped_files(event.mimeData(), self.drop_kinds):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._set_drop_active(False)
        event.accept()

    def dropEvent(self, event) -> None:
        files = dropped_files(event.mimeData(), self.drop_kinds)
        self._set_drop_active(False)
        if not files:
            event.ignore()
            return
        event.acceptProposedAction()
        # Run after the drag finishes so the file manager is not frozen behind a modal dialog.
        QTimer.singleShot(0, lambda item=files[0]: self.handle_dropped_file(*item))

    def handle_dropped_file(self, path: str, kind: str) -> None:
        if kind == IMAGE:
            self.handle_dropped_image(path)
        else:
            self.handle_dropped_csv(path)

    def handle_dropped_csv(self, path: str) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def handle_dropped_image(self, path: str) -> None:  # pragma: no cover - overridden
        raise NotImplementedError
