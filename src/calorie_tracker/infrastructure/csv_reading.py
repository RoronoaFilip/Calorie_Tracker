"""Tolerant CSV reading shared by the food and diary importers."""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

_CANDIDATE_DELIMITERS = (",", ";", "\t", "|")
_SAMPLE_LINES = 40
_UNIT_SUFFIX = re.compile(r"\s*(?:kcal|grams?|gr|g)\.?$", re.IGNORECASE)


class CsvReadError(ValueError):
    """The file could not be decoded or parsed as CSV."""


@dataclass(frozen=True)
class CsvTable:
    rows: list[list[str]]
    delimiter: str
    encoding: str


def _decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16"
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1"), "latin-1"


def _field_counts(text: str, delimiter: str) -> list[int] | None:
    counts: list[int] = []
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        for row in reader:
            if any(cell.strip() for cell in row):
                counts.append(len(row))
            if len(counts) >= _SAMPLE_LINES:
                break
    except csv.Error:
        return None
    return counts


def detect_delimiter(text: str) -> str:
    """Pick the delimiter that splits the sample lines into the most consistent columns."""
    best, best_score = ",", 0
    for delimiter in _CANDIDATE_DELIMITERS:
        counts = _field_counts(text, delimiter)
        if not counts:
            continue
        width, lines = Counter(count for count in counts if count > 1).most_common(1)[0] \
            if any(count > 1 for count in counts) else (0, 0)
        score = width * lines
        if score > best_score:
            best, best_score = delimiter, score
    return best


def read_csv_rows(path: Path | str) -> CsvTable:
    """Read a CSV with automatic encoding and delimiter detection (comma, semicolon, tab, pipe)."""
    text, encoding = _decode(Path(path).read_bytes())
    delimiter = detect_delimiter(text)
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
    except csv.Error as error:
        raise CsvReadError(f"CSV syntax error: {error}") from error
    return CsvTable(rows, delimiter, encoding)


def read_csv_text(text: str) -> CsvTable:
    """Read CSV that was pasted as text (no file), with the same delimiter detection as for files."""
    text = text.lstrip("\ufeff")
    delimiter = detect_delimiter(text)
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
    except csv.Error as error:
        raise CsvReadError(f"CSV syntax error: {error}") from error
    return CsvTable(rows, delimiter, "text")


def parse_decimal(text: str) -> Decimal:
    """Parse '45', '45.5', '45,5', '1 234,5', '45 g' or '120 kcal'; raises InvalidOperation."""
    value = text.replace("\u00a0", " ").strip()
    value = _UNIT_SUFFIX.sub("", value).replace(" ", "")
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif value.count(",") > 1:
        value = value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
    return Decimal(value)


def delimiter_name(delimiter: str) -> str:
    return {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}.get(delimiter, repr(delimiter))
