import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import uuid

from calorie_tracker.domain.nutrition import Nutrients, ZERO
from calorie_tracker.domain.recipes import Food
from .repositories import FoodRepository
from .source_map import CSV_HEADER_ROW, EXCLUDED_ICE_CREAM_NAMES, FOOD_NAME_HEADER, NUTRIENT_HEADERS

FOOD_CSV_FORMAT_GUIDANCE = (
    "Expected header columns on row 5: "
    + ", ".join((FOOD_NAME_HEADER, *NUTRIENT_HEADERS.values()))
    + ". Values must use the explicitly mapped per-100g columns."
)


class ImportFormatError(ValueError):
    """The source CSV does not have the explicitly reviewed layout."""


@dataclass(frozen=True)
class ImportFood:
    food: Food
    source_key: str
    source_row: int


@dataclass(frozen=True)
class ImportReport:
    rows_read: int
    importable: int
    duplicate_names: int
    blank_names: int
    malformed_rows: int
    excluded_ice_cream_rows: int
    ignored_headers: tuple[str, ...]
    row_errors: tuple[str, ...]


@dataclass(frozen=True)
class ImportPreview:
    foods: tuple[ImportFood, ...]
    report: ImportReport


@dataclass(frozen=True)
class ImportResult:
    imported: int
    already_present: int
    name_conflicts: int


class CsvFoodImporter:
    def __init__(self, repository: FoodRepository):
        self.repository = repository

    def preview(self, path: Path | str) -> ImportPreview:
        try:
            with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream, strict=True))
        except csv.Error as error:
            raise ImportFormatError(
                f"CSV syntax error: {error}. {FOOD_CSV_FORMAT_GUIDANCE}"
            ) from error
        if len(rows) <= CSV_HEADER_ROW:
            raise ImportFormatError(
                "This file is not in the food catalogue import format. The header must be on row 5 and include "
                f"'{FOOD_NAME_HEADER}' plus the mapped per-100g nutrition columns. {FOOD_CSV_FORMAT_GUIDANCE}"
            )
        header = rows[CSV_HEADER_ROW]
        required_headers = (FOOD_NAME_HEADER, *NUTRIENT_HEADERS.values())
        missing = [column for column in required_headers if column not in header]
        duplicates = [column for column in required_headers if header.count(column) > 1]
        if duplicates:
            raise ImportFormatError(
                "The food CSV contains duplicate required column(s): "
                + ", ".join(duplicates)
                + ".\n\n"
                + FOOD_CSV_FORMAT_GUIDANCE
            )
        if missing:
            raise ImportFormatError(
                "This file is not in the food catalogue import format. Missing required column(s): "
                + ", ".join(missing)
                + ".\n\n"
                + FOOD_CSV_FORMAT_GUIDANCE
            )
        positions = {name: header.index(name) for name in required_headers}
        ignored = tuple(name for name in header if name not in required_headers)
        foods: list[ImportFood] = []
        errors: list[str] = []
        seen_names: set[str] = set()
        duplicates = blank_names = malformed = excluded_ice_cream_rows = rows_read = 0
        for source_row, values in enumerate(rows[CSV_HEADER_ROW + 1:], start=CSV_HEADER_ROW + 2):
            if not values or not any(value.strip() for value in values):
                continue
            rows_read += 1
            name = values[positions[FOOD_NAME_HEADER]].strip() if len(values) > positions[FOOD_NAME_HEADER] else ""
            if not name:
                blank_names += 1
                continue
            normalized = name.casefold()
            if normalized in seen_names:
                duplicates += 1
                continue
            seen_names.add(normalized)
            if normalized in EXCLUDED_ICE_CREAM_NAMES:
                excluded_ice_cream_rows += 1
                continue
            nutrients: dict[str, Decimal] = {}
            row_error: str | None = None
            for field, column in NUTRIENT_HEADERS.items():
                position = positions[column]
                raw = values[position].strip() if len(values) > position else ""
                try:
                    value = Decimal(raw)
                    if not value.is_finite() or value < ZERO:
                        raise InvalidOperation
                    nutrients[field] = value
                except (InvalidOperation, ValueError):
                    row_error = f"Row {source_row} ({name}): invalid non-negative number in {column}."
                    break
            if row_error:
                malformed += 1
                errors.append(row_error)
                continue
            source_key = "csv:food:" + normalized
            stable_id = str(uuid.uuid5(uuid.NAMESPACE_URL, source_key))
            foods.append(ImportFood(
                Food(stable_id, name, Nutrients(**nutrients)), source_key, source_row
            ))
        report = ImportReport(
            rows_read, len(foods), duplicates, blank_names, malformed,
            excluded_ice_cream_rows, ignored, tuple(errors)
        )
        return ImportPreview(tuple(foods), report)

    def apply(self, preview: ImportPreview) -> ImportResult:
        imported, already_present, name_conflicts = self.repository.seed_foods(tuple(
            (entry.food, entry.source_key, entry.source_row) for entry in preview.foods
        ))
        return ImportResult(imported, already_present, name_conflicts)
