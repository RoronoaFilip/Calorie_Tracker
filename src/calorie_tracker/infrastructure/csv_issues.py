"""Cell-level problems found in a CSV, so a repair screen can point at exactly what to fix."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .csv_headers import analyze_headers


@dataclass(frozen=True)
class CsvIssue:
    """One problem. ``row``/``column`` are 0-based positions in the table; ``column`` None means the whole row."""

    row: int
    column: int | None
    message: str


def header_issues(
    rows: Sequence[Sequence[str]],
    aliases: Mapping[str, Sequence[str]],
    required: Sequence[str],
    labels: Mapping[str, str],
) -> tuple[CsvIssue, ...]:
    """Explain why no row qualifies as a header: which required columns the best candidate row lacks."""
    if not any(any(cell.strip() for cell in row) for row in rows):
        return (CsvIssue(0, None, "The file is empty."),)
    best_index, best_found = 0, -1
    for index, row in enumerate(rows[:50]):
        found = sum(field in analyze_headers(row, aliases).positions for field in required)
        if found > best_found:
            best_index, best_found = index, found
    analysis = analyze_headers(rows[best_index], aliases)
    available = set(analysis.positions) | set(analysis.duplicates)
    wanted = ", ".join(labels.get(field, field) for field in required)
    issues: list[CsvIssue] = []
    if best_found <= 0:
        issues.append(CsvIssue(
            best_index, None,
            f"No column names recognised. Make this row the header with: {wanted}.",
        ))
    for field in required:
        if field not in available and best_found > 0:
            label = labels.get(field, field)
            issues.append(CsvIssue(
                best_index, None,
                f"Required column “{label}” not found. Rename one of the headers in this row to “{label}”.",
            ))
    for field in analysis.duplicates:
        label = labels.get(field, field)
        issues.append(CsvIssue(
            best_index, None, f"More than one column matches “{label}”. Rename or clear all but one.",
        ))
    return tuple(issues)


def cell_text(rows: Sequence[Sequence[str]], row: int, column: int) -> str:
    return rows[row][column].strip() if row < len(rows) and column < len(rows[row]) else ""
