"""Explain pasted CSV text before it is imported: what it is, what will be used, and where the problems are.

Nothing here saves or changes anything. It reuses the importers' own checks (``preview_table`` and
``issues_for``) so the explanation can never disagree with the review screen that follows, and it maps their
row/column positions back to character offsets in the pasted text so a text box can highlight them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .csv_headers import FIELD_LABELS
from .csv_kind import CsvKind, classify_rows
from .csv_reading import CsvReadError, CsvTable, read_csv_text

MAX_ROWS = 500
_HEADER_SEARCH_ROWS = 50
_KIND_LABELS = {CsvKind.FOODS: "Foods", CsvKind.DIARY: "Diary", CsvKind.RECIPES: "Recipes"}
NO_HEADER_MESSAGE = "Paste a header row so the app knows what this is (see ? for the formats)."


@dataclass(frozen=True)
class CellSpan:
    start: int  # character offset in the text
    end: int    # exclusive


class PasteState(StrEnum):
    IGNORED = "ignored"
    HEADER = "header"
    OK = "ok"
    PROBLEM = "problem"
    WARNING = "warning"


@dataclass(frozen=True)
class Highlight:
    start: int
    end: int
    state: PasteState
    tooltip: str = ""
    emphasis: bool = False  # True: one cell inside a row (underlined); False: the whole row or header cell


@dataclass(frozen=True)
class PasteAnalysis:
    kind: CsvKind
    summary: str
    highlights: tuple[Highlight, ...] = ()
    problem_count: int = 0
    warning_count: int = 0
    read_error: str | None = None


def locate_cells(text: str, delimiter: str) -> list[list[CellSpan]]:
    """Character offsets of every cell, one list per parsed CSV row (blank lines give ``[]``).

    Index *n* lines up with ``read_csv_text(text).rows[n]``; quoted cells (including multi-line ones) are
    covered from the opening to the closing quote.
    """
    rows: list[list[CellSpan]] = []
    length = len(text)
    position = 0
    while position < length:
        if text[position] in "\r\n":
            rows.append([])
            position = _skip_newline(text, position)
            continue
        cells: list[CellSpan] = []
        while True:
            start = position
            if position < length and text[position] == '"':
                position += 1
                while position < length:
                    if text[position] == '"':
                        if position + 1 < length and text[position + 1] == '"':
                            position += 2
                            continue
                        position += 1
                        break
                    position += 1
            while position < length and text[position] not in (delimiter, "\r", "\n"):
                position += 1
            cells.append(CellSpan(start, position))
            if position < length and text[position] == delimiter:
                position += 1
                continue
            break
        rows.append(cells)
        position = _skip_newline(text, position)
    return rows


def _skip_newline(text: str, position: int) -> int:
    if position < len(text) and text[position] == "\r":
        position += 1
        if position < len(text) and text[position] == "\n":
            position += 1
    elif position < len(text) and text[position] == "\n":
        position += 1
    return position


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def analyze_paste(
    text: str, importers: Mapping[CsvKind, Any], *, max_rows: int = MAX_ROWS
) -> PasteAnalysis:
    """Describe ``text``. ``importers`` maps each ``CsvKind`` to its importer (foods, diary, recipes)."""
    if not text.strip():
        return PasteAnalysis(CsvKind.UNKNOWN, "")
    stripped = text.lstrip("\ufeff")
    offset = len(text) - len(stripped)
    try:
        table = read_csv_text(stripped)
    except CsvReadError as error:
        return PasteAnalysis(CsvKind.UNKNOWN, str(error), read_error=str(error))
    capped = len(table.rows) > max_rows + _HEADER_SEARCH_ROWS
    if capped:
        table = CsvTable(table.rows[: max_rows + _HEADER_SEARCH_ROWS], table.delimiter, table.encoding)
    kind = classify_rows(table.rows)
    if kind is CsvKind.UNKNOWN or kind not in importers:
        return PasteAnalysis(CsvKind.UNKNOWN, NO_HEADER_MESSAGE)
    importer = importers[kind]
    try:
        preview = importer.preview_table(table)
        issues = importer.issues_for(table)
    except ValueError as error:  # the importers' format errors all derive from ValueError
        return PasteAnalysis(kind, str(error).split("\n", 1)[0])

    spans = locate_cells(stripped, table.delimiter)
    header_index = preview.header_row - 1
    matched = {match.column: match.field for match in preview.column_matches}
    highlights: list[Highlight] = []

    def row_span(index: int) -> tuple[int, int] | None:
        cells = spans[index] if index < len(spans) else []
        return (cells[0].start + offset, cells[-1].end + offset) if cells else None

    ignored_lines = 0
    for index in range(min(header_index, len(table.rows))):
        span = row_span(index)
        if span and any(cell.strip() for cell in table.rows[index]):
            ignored_lines += 1
            highlights.append(Highlight(*span, PasteState.IGNORED, "Not part of the import (it is before the header row)."))

    unused: list[str] = []
    for column, cell in enumerate(table.rows[header_index] if header_index < len(table.rows) else []):
        if column >= len(spans[header_index]):
            break
        span = spans[header_index][column]
        if column in matched:
            label = FIELD_LABELS.get(matched[column], matched[column])
            highlights.append(Highlight(span.start + offset, span.end + offset, PasteState.HEADER, f"Used as: {label}"))
        elif cell.strip():
            unused.append(cell.strip())

    problem_rows: dict[int, list[str]] = {}
    for issue in issues:
        problem_rows.setdefault(issue.row, []).append(issue.message)
    warnings = _warnings(kind, preview)  # table row index -> message
    last_row = header_index + max_rows
    data_rows = [
        index for index in range(header_index + 1, len(table.rows))
        if any(cell.strip() for cell in table.rows[index])
    ]
    ok_count = 0
    for index in data_rows:
        span = row_span(index)
        if span is None:
            continue
        if index in problem_rows:
            state, tooltip = PasteState.PROBLEM, " ".join(problem_rows[index])
        elif index in warnings:
            state, tooltip = PasteState.WARNING, warnings[index]
        else:
            state, tooltip = PasteState.OK, ""
            ok_count += 1
        if index <= last_row:
            highlights.append(Highlight(*span, state, tooltip))
    for issue in issues:
        if issue.column is not None and issue.row <= last_row and issue.row < len(spans) and issue.column < len(spans[issue.row]):
            cell = spans[issue.row][issue.column]
            highlights.append(Highlight(cell.start + offset, cell.end + offset, PasteState.PROBLEM, issue.message, True))

    first = min(issues, key=lambda item: (item.row, item.column if item.column is not None else -1), default=None)
    summary = _summary(
        kind, len(data_rows), ok_count, len(issues), first, matched, len(warnings), unused, ignored_lines, capped, max_rows
    )
    return PasteAnalysis(kind, summary, tuple(highlights), len(issues), len(warnings))


def _warnings(kind: CsvKind, preview: Any) -> dict[int, str]:
    """Rows that are not errors in the text but will not import as they are (table row index -> message)."""
    result: dict[int, str] = {}
    if kind is CsvKind.DIARY:
        for row in preview.rows:
            if row.error and not row.value_problems:
                message = row.error
                if row.suggestions and row.suggestions[0].confident:
                    message += f" It will be suggested as '{row.suggestions[0].name}' in the review, for you to confirm."
                result[row.source_row - 1] = message
    elif kind is CsvKind.FOODS:
        for row in preview.rows:
            if row.status in ("duplicate", "excluded"):
                result[row.source_row - 1] = row.message
    elif kind is CsvKind.RECIPES:
        for item in preview.items:
            if item.status == "exists":
                for source_row in item.source_rows:
                    result[source_row - 1] = item.message
    return result


def _summary(
    kind: CsvKind, total: int, ok: int, problems: int, first: Any, matched: Mapping[int, str],
    warnings: int, unused: Sequence[str], ignored_lines: int, capped: bool, max_rows: int,
) -> str:
    label = _KIND_LABELS.get(kind, kind.value)
    needs_attention = problems or warnings
    text = f"{'!' if needs_attention else '✓'} {label}: "
    text += f"{ok} of {_plural(total, 'row')} ready" if needs_attention else f"{_plural(total, 'row')} ready"
    if problems:
        where = ""
        if first is not None:
            field = matched.get(first.column) if first.column is not None else None
            where = f" (row {first.row + 1}" + (f", {FIELD_LABELS.get(field, field)}" if field else "") + ")"
        text += f", {_plural(problems, 'problem')}{where}"
    if warnings:
        text += f", {_plural(warnings, 'row')} to look at in the review"
    text += "."
    if unused:
        text += f" Not used: {', '.join(unused)}."
    if ignored_lines:
        text += f" {_plural(ignored_lines, 'line')} before the header ignored."
    if capped:
        text += f" Showing the first {max_rows} rows."
    return text
