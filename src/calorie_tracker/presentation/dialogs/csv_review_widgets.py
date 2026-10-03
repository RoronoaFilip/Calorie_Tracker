"""Shared pieces of the two CSV review screens: file-reading summary and row colours."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from calorie_tracker.infrastructure.csv_headers import ColumnMatch
from calorie_tracker.infrastructure.csv_reading import delimiter_name

READY_BG = QColor("#e1f3e8")
WARNING_BG = QColor("#fff0d2")
ERROR_BG = QColor("#fbe1e4")
SKIPPED_BG = QColor("#e7ebf2")

_GOOD, _WARN, _BAD, _MUTED = "#1f7a4d", "#9a6700", "#b53d48", "#5b6778"
GOOD_TEXT, BAD_TEXT = _GOOD, _BAD


def mapping_html(
    matches: Sequence[ColumnMatch],
    ignored: Sequence[str],
    header_row: int,
    delimiter: str,
    expected: Sequence[tuple[str, str, bool]],
) -> str:
    """Describe how each expected field was found: (field, label, required) per entry."""
    by_field = {match.field: match for match in matches}
    lines = [
        f"<b>How your file was read</b> — header on row {header_row}, "
        f"{escape(delimiter_name(delimiter))}-separated"
    ]
    for field, label, required in expected:
        match = by_field.get(field)
        if match is None:
            if required:
                lines.append(f"<span style='color:{_BAD}'>✕ <b>{escape(label)}</b> — column not found</span>")
            else:
                lines.append(f"<span style='color:{_MUTED}'>– {escape(label)} — not in this file (optional)</span>")
        elif match.how == "approximate":
            lines.append(
                f"<span style='color:{_WARN}'>≈ <b>{escape(label)}</b> ← “{escape(match.header)}”"
                " (approximate match — check it is right)</span>"
            )
        else:
            lines.append(f"<span style='color:{_GOOD}'>✓ <b>{escape(label)}</b> ← “{escape(match.header)}”</span>")
    shown = [value for value in ignored if value.strip()]
    if shown:
        lines.append(
            f"<span style='color:{_MUTED}'>Ignored columns: "
            + ", ".join(f"“{escape(value)}”" for value in shown) + "</span>"
        )
    return "<br>".join(lines)


def make_mapping_panel(html: str) -> QFrame:
    panel = QFrame()
    panel.setObjectName("card")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(14, 10, 14, 10)
    label = QLabel(html)
    label.setObjectName("csvMappingSummary")
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    layout.addWidget(label)
    return panel
