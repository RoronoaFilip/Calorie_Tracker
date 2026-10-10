"""Live highlight for the raw-input box: shows what will be imported and where the problems are.

The text is never changed (the highlight is a set of extra selections), so undo keeps working. All the
thinking happens in ``infrastructure.paste_analysis``; this module only paints its result.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QTextEdit, QToolTip

from calorie_tracker.infrastructure.csv_kind import CsvKind
from calorie_tracker.infrastructure.paste_analysis import Highlight, PasteAnalysis, PasteState, analyze_paste
from calorie_tracker.presentation.dialogs.csv_review_widgets import BAD_TEXT, ERROR_BG, READY_BG, WARNING_BG

DEBOUNCE_MS = 300
_MUTED_TEXT = QColor("#5b6778")
_HEADER_BG = QColor("#dfe8f5")
_WARN_TEXT = QColor("#9a6700")


def _document_positions(text: str) -> list[int] | None:
    """Python string index -> QTextDocument position (UTF-16 units); ``None`` when they are the same."""
    if all(ord(char) <= 0xFFFF for char in text):
        return None
    positions = [0]
    total = 0
    for char in text:
        total += 2 if ord(char) > 0xFFFF else 1
        positions.append(total)
    return positions


class PasteHighlighter(QObject):
    """Keeps a status label and the highlight of ``editor`` in step with its text (debounced)."""

    def __init__(
        self, editor: QPlainTextEdit, status: QLabel, importers: Mapping[CsvKind, Any], parent: QObject | None = None
    ):
        super().__init__(parent or editor)
        self.editor = editor
        self.status = status
        self.importers = importers
        self.analysis = PasteAnalysis(CsvKind.UNKNOWN, "")
        self._text = ""
        self._positions: list[int] | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self.refresh)
        editor.textChanged.connect(lambda: self._timer.start())
        editor.viewport().installEventFilter(self)
        self.refresh()

    def refresh(self) -> None:
        """Analyse the current text now and repaint (also what the debounce timer calls)."""
        self._timer.stop()
        self._text = self.editor.toPlainText()
        self._positions = _document_positions(self._text)
        self.analysis = analyze_paste(self._text, self.importers)
        self.status.setText(self.analysis.summary)
        self.status.setAccessibleDescription(self.analysis.summary)
        self._paint()

    # ---- painting -------------------------------------------------------------------------------

    @staticmethod
    def _format(highlight: Highlight) -> QTextCharFormat:
        fmt = QTextCharFormat()
        state = highlight.state
        if state is PasteState.IGNORED:
            fmt.setForeground(_MUTED_TEXT)
        elif state is PasteState.HEADER:
            fmt.setBackground(_HEADER_BG)
            fmt.setFontWeight(QFont.Weight.Bold)
        elif state is PasteState.OK:
            fmt.setBackground(READY_BG)
        elif state is PasteState.PROBLEM:
            fmt.setBackground(ERROR_BG)
        elif state is PasteState.WARNING:
            fmt.setBackground(WARNING_BG)
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
            fmt.setUnderlineColor(_WARN_TEXT)
        if highlight.emphasis:
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            fmt.setUnderlineColor(QColor(BAD_TEXT))
            fmt.setFontWeight(QFont.Weight.Bold)
        return fmt

    def _document_position(self, index: int) -> int:
        if self._positions is None:
            return index
        return self._positions[min(max(index, 0), len(self._positions) - 1)]

    def _paint(self) -> None:
        document = self.editor.document()
        limit = max(document.characterCount() - 1, 0)
        selections = []
        for highlight in self.analysis.highlights:
            start = min(self._document_position(highlight.start), limit)
            end = min(self._document_position(highlight.end), limit)
            if end <= start:
                continue  # an empty cell has nothing to paint; its row is still tinted
            cursor = QTextCursor(document)
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format = self._format(highlight)
            selections.append(selection)
        self.editor.setExtraSelections(selections)

    # ---- hover message --------------------------------------------------------------------------

    def _string_index(self, document_position: int) -> int:
        if self._positions is None:
            return document_position
        index = 0
        while index + 1 < len(self._positions) and self._positions[index + 1] <= document_position:
            index += 1
        return index

    def tooltip_at(self, document_position: int) -> str:
        """The message of the most specific highlight under a text position ('' when there is none)."""
        index = self._string_index(document_position)
        covering = [
            highlight for highlight in self.analysis.highlights
            if highlight.tooltip and highlight.start <= index < highlight.end
        ]
        if not covering:
            return ""
        best = min(covering, key=lambda item: (not item.emphasis, item.end - item.start))
        return best.tooltip

    def eventFilter(self, watched, event) -> bool:
        if watched is self.editor.viewport() and event.type() == QEvent.Type.ToolTip:
            message = self.tooltip_at(self.editor.cursorForPosition(event.pos()).position())
            if message:
                QToolTip.showText(event.globalPos(), message, self.editor.viewport())
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().eventFilter(watched, event)
