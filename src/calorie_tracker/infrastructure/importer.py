import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import uuid

from calorie_tracker.domain.nutrition import Nutrients, ZERO
from calorie_tracker.domain.recipes import Food
from .csv_headers import FOOD_FIELD_ALIASES, match_headers
from .repositories import FoodRepository
from .source_map import EXCLUDED_ICE_CREAM_NAMES

FOOD_REQUIRED_FIELDS = ("food_name", "calories", "protein", "fat", "carbohydrates")
NUTRIENT_FIELDS = tuple(field for field in FOOD_FIELD_ALIASES if field not in ("food_name",))
FIELD_LABELS = {
    "food_name": "food name", "calories": "calories / 100g", "protein": "protein / 100g",
    "fat": "fat / 100g", "carbohydrates": "carbohydrates / 100g",
}

FOOD_CSV_FORMAT_GUIDANCE = (
    "Expected header columns within the first 50 rows include food_name, calories / 100g, "
    "protein / 100g, fat / 100g, and carbohydrates / 100g. Equivalent documented aliases are accepted; "
    "nutrition values must be per 100g."
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
        header_index, positions, ignored = self._find_header(rows)
        header = rows[header_index]
        foods: list[ImportFood] = []
        errors: list[str] = []
        seen_names: set[str] = set()
        duplicates = blank_names = malformed = excluded_ice_cream_rows = rows_read = 0
        for source_row, values in enumerate(rows[header_index + 1:], start=header_index + 2):
            if not values or not any(value.strip() for value in values):
                continue
            rows_read += 1
            name_position = positions["food_name"]
            name = values[name_position].strip() if len(values) > name_position else ""
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
            for field in NUTRIENT_FIELDS:
                if field not in positions:
                    nutrients[field] = ZERO
                    continue
                position = positions[field]
                raw = values[position].strip() if len(values) > position else ""
                if not raw and field not in ("calories", "protein", "fat", "carbohydrates"):
                    nutrients[field] = ZERO
                    continue
                try:
                    value = Decimal(raw)
                    if not value.is_finite() or value < ZERO:
                        raise InvalidOperation
                    nutrients[field] = value
                except (InvalidOperation, ValueError):
                    row_error = f"Row {source_row} ({name}): invalid non-negative number in {header[position]} or a required value is blank."
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

    @staticmethod
    def _find_header(rows: list[list[str]]) -> tuple[int, dict[str, int], tuple[str, ...]]:
        required = set(FOOD_REQUIRED_FIELDS)
        for index, row in enumerate(rows[:50]):
            positions, duplicates, ignored = match_headers(row, FOOD_FIELD_ALIASES)
            available = set(positions) | set(duplicates)
            if not required.issubset(available):
                continue
            if duplicates:
                duplicate_labels = ", ".join(FIELD_LABELS.get(field, field) for field in duplicates)
                raise ImportFormatError(
                    "The food CSV contains duplicate headers for the same field: "
                    + duplicate_labels + ".\n\n" + FOOD_CSV_FORMAT_GUIDANCE
                )
            return index, positions, ignored
        raise ImportFormatError(
            "Could not find a food catalogue header with all required fields within the first 50 rows. "
            + FOOD_CSV_FORMAT_GUIDANCE
        )

    def apply(self, preview: ImportPreview) -> ImportResult:
        imported, already_present, name_conflicts = self.repository.seed_foods(tuple(
            (entry.food, entry.source_key, entry.source_row) for entry in preview.foods
        ))
        return ImportResult(imported, already_present, name_conflicts)
