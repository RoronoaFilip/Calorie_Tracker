"""Drag-and-drop support for opening CSV files, photos and zip files from the file manager."""

from __future__ import annotations

from collections.abc import Collection

from PySide6.QtCore import QMimeData, QTimer, Qt

from calorie_tracker.infrastructure.file_kinds import CSV, IMAGE, ZIP, classify_file


def dropped_files(mime: QMimeData, accepted: Collection[str]) -> list[tuple[str, str]]:
    """Return ``(path, kind)`` for each local file in a drag whose kind (csv/image/zip) is in ``accepted``."""
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
    """Mix in before a QWidget base. Set ``drop_kinds`` to the kinds the widget takes (csv, image, zip).

    Everything dropped at once is passed to ``handle_dropped_files``. By default that handles only the first
    file: a CSV calls ``handle_dropped_csv(path)``, a photo ``handle_dropped_image(path)`` and a zip
    ``handle_dropped_zip(path)``. Widgets that take several files override ``handle_dropped_files``.
    The file's content decides which kind it is, so photos without (or with the wrong) extension still work.
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
        QTimer.singleShot(0, lambda items=tuple(files): self.handle_dropped_files(list(items)))

    def handle_dropped_files(self, files: list[tuple[str, str]]) -> None:
        """Called with every accepted ``(path, kind)`` of a drop; the default takes only the first."""
        self.handle_dropped_file(*files[0])

    def handle_dropped_file(self, path: str, kind: str) -> None:
        if kind == IMAGE:
            self.handle_dropped_image(path)
        elif kind == ZIP:
            self.handle_dropped_zip(path)
        else:
            self.handle_dropped_csv(path)

    def handle_dropped_csv(self, path: str) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def handle_dropped_image(self, path: str) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def handle_dropped_zip(self, path: str) -> None:  # pragma: no cover - overridden
        raise NotImplementedError
