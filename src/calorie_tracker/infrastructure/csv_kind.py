"""Decide whether a CSV holds foods, diary entries or recipes by looking at its header row."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path

from .csv_headers import DIARY_FIELD_ALIASES, FOOD_FIELD_ALIASES, RECIPE_FIELD_ALIASES, analyze_headers
from .csv_reading import CsvReadError, read_csv_rows, read_csv_text
from .importer import FOOD_REQUIRED_FIELDS
from .recipe_csv_importer import REQUIRED_FIELDS as RECIPE_REQUIRED_FIELDS

_HEADER_SEARCH_ROWS = 50  # the importers look for their header row among the first 50 rows too
DIARY_REQUIRED_FIELDS = ("food_name", "amount_g")


class CsvKind(StrEnum):
    FOODS = "foods"
    DIARY = "diary"
    RECIPES = "recipes"
    UNKNOWN = "unknown"


def _matching_kinds(row: Sequence[str]) -> set[CsvKind]:
    kinds: set[CsvKind] = set()
    for kind, aliases, required in (
        (CsvKind.FOODS, FOOD_FIELD_ALIASES, FOOD_REQUIRED_FIELDS),
        (CsvKind.DIARY, DIARY_FIELD_ALIASES, DIARY_REQUIRED_FIELDS),
        (CsvKind.RECIPES, RECIPE_FIELD_ALIASES, RECIPE_REQUIRED_FIELDS),
    ):
        analysis = analyze_headers(row, aliases)
        if set(required) <= set(analysis.positions) | set(analysis.duplicates):
            kinds.add(kind)
    return kinds


def classify_rows(rows: Sequence[Sequence[str]]) -> CsvKind:
    """Classify parsed CSV rows by the first row that looks like a header for any kind.

    A recipe header wins over the others because it needs the explicit ``ingredient`` column (a recipe file
    also looks like a diary file: name, amount). Foods and diary at once (for example a diary export that
    also carries nutrient columns) is genuinely ambiguous, so it stays ``UNKNOWN`` and the person is asked.
    """
    for row in rows[:_HEADER_SEARCH_ROWS]:
        if not any(cell.strip() for cell in row):
            continue
        kinds = _matching_kinds(row)
        if not kinds:
            continue
        if CsvKind.RECIPES in kinds:
            return CsvKind.RECIPES
        return next(iter(kinds)) if len(kinds) == 1 else CsvKind.UNKNOWN
    return CsvKind.UNKNOWN


def classify_csv(path: Path | str) -> CsvKind:
    try:
        return classify_rows(read_csv_rows(path).rows)
    except (CsvReadError, OSError):
        return CsvKind.UNKNOWN


def classify_csv_text(text: str) -> CsvKind:
    try:
        return classify_rows(read_csv_text(text).rows)
    except CsvReadError:
        return CsvKind.UNKNOWN
