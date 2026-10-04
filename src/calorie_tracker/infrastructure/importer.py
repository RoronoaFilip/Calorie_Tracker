from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import uuid

from calorie_tracker.domain.nutrition import BASIS_COUNT, BASIS_GRAMS, Nutrients, ZERO
from calorie_tracker.domain.recipes import Food
from .csv_headers import FOOD_FIELD_ALIASES, ColumnMatch, analyze_headers, describe_closest_header, normalize_header
from .csv_issues import CsvIssue, cell_text, header_issues
from .csv_reading import read_csv_text, CsvReadError, CsvTable, parse_decimal, read_csv_rows
from .repositories import FoodRepository
from .source_map import EXCLUDED_ICE_CREAM_NAMES

FOOD_REQUIRED_FIELDS = ("food_name", "calories", "protein", "fat", "carbohydrates")
NUTRIENT_FIELDS = tuple(field for field in FOOD_FIELD_ALIASES if field not in ("food_name", "basis"))

_GRAM_BASIS_WORDS = frozenset({"", "g", "gram", "grams", "100g", "100grams", "per100g", "per100grams", "weight"})
_COUNT_BASIS_WORDS = frozenset({
    "count", "percount", "item", "items", "peritem", "each", "piece", "pieces", "pcs", "pc",
    "unit", "units", "quantity", "qty", "serving", "perserving",
})


def parse_basis(text: str) -> str | None:
    """'g', 'per 100 g'... -> "g"; 'count', 'per item', 'each'... -> "count"; anything else -> None."""
    key = normalize_header(text)
    if key in _GRAM_BASIS_WORDS:
        return BASIS_GRAMS
    if key in _COUNT_BASIS_WORDS:
        return BASIS_COUNT
    return None

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
    """The source CSV does not have the explicitly reviewed layout.

    ``issues`` pin the problem to cells and ``table`` holds the rows that were read (when the file could be
    read at all), so a repair screen can let the user fix them in memory.
    """

    def __init__(self, message: str, issues: tuple[CsvIssue, ...] = (), table: CsvTable | None = None):
        super().__init__(message)
        self.issues = issues
        self.table = table


@dataclass(frozen=True)
class ImportFood:
    food: Food
    source_key: str
    source_row: int


@dataclass(frozen=True)
class InvalidImportFood:
    food: Food
    source_key: str
    source_row: int
    fields_to_correct: tuple[str, ...]
    errors: tuple[str, ...]


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
class ImportRowReview:
    """One CSV row as shown in the review table (status: ready, needs_correction, duplicate, excluded)."""

    source_row: int
    name: str
    values: dict[str, str]
    status: str
    message: str = ""


@dataclass(frozen=True)
class ImportPreview:
    foods: tuple[ImportFood, ...]
    report: ImportReport
    invalid_foods: tuple[InvalidImportFood, ...] = ()
    rows: tuple[ImportRowReview, ...] = ()
    column_matches: tuple[ColumnMatch, ...] = ()
    header_row: int = 1
    delimiter: str = ","


@dataclass(frozen=True)
class ImportResult:
    imported: int
    already_present: int
    name_conflicts: int


class CsvFoodImporter:
    def __init__(self, repository: FoodRepository):
        self.repository = repository

    def read(self, path: Path | str) -> CsvTable:
        try:
            return read_csv_rows(path)
        except CsvReadError as error:
            raise ImportFormatError(f"{error}. {FOOD_CSV_FORMAT_GUIDANCE}") from error

    def read_text(self, text: str) -> CsvTable:
        """The same as ``read`` for CSV text that was pasted instead of chosen as a file."""
        try:
            return read_csv_text(text)
        except CsvReadError as error:
            raise ImportFormatError(f"{error}. {FOOD_CSV_FORMAT_GUIDANCE}") from error

    def preview(self, path: Path | str) -> ImportPreview:
        return self.preview_table(self.read(path))

    def issues_for(self, table: CsvTable) -> tuple[CsvIssue, ...]:
        """Every missing-column or bad-value problem in ``table``, as cell positions (empty when it is clean)."""
        try:
            preview = self.preview_table(table)
        except ImportFormatError as error:
            return error.issues or (CsvIssue(0, None, str(error)),)
        positions = {match.field: match.column for match in preview.column_matches}
        issues: list[CsvIssue] = []
        for invalid in preview.invalid_foods:
            row = invalid.source_row - 1
            for field in invalid.fields_to_correct:
                column = positions.get(field)
                if column is None:
                    continue
                raw = cell_text(table.rows, row, column)
                if field == "food_name":
                    message = "Food name is blank."
                elif field == "basis":
                    message = f"“{raw}” is not a basis. Use g (values per 100 g) or count (values per item)."
                elif raw:
                    message = f"“{raw}” is not a valid number. Enter 0 or more (per 100 g)."
                else:
                    message = "This value is required and is empty. Enter the amount per 100 g."
                issues.append(CsvIssue(row, column, message))
        return tuple(issues)

    def preview_table(self, table: CsvTable) -> ImportPreview:
        """Validate already-read rows. Used for the first read and again after in-memory edits."""
        rows = table.rows
        try:
            header_index, analysis = self._find_header(rows)
        except ImportFormatError as error:
            error.table = table
            raise
        positions, ignored = analysis.positions, analysis.ignored
        header = rows[header_index]
        reviews: list[ImportRowReview] = []
        foods: list[ImportFood] = []
        invalid_foods: list[InvalidImportFood] = []
        errors: list[str] = []
        seen_names: set[str] = set()
        duplicates = blank_names = malformed = excluded_ice_cream_rows = rows_read = 0
        for source_row, values in enumerate(rows[header_index + 1:], start=header_index + 2):
            if not values or not any(value.strip() for value in values):
                continue
            rows_read += 1
            name_position = positions["food_name"]
            name = values[name_position].strip() if len(values) > name_position else ""
            normalized = name.casefold()
            if not name:
                blank_names += 1
            elif normalized in seen_names:
                duplicates += 1
                reviews.append(ImportRowReview(
                    source_row, name, {}, "duplicate", "Same name as an earlier row; skipped."
                ))
                continue
            else:
                seen_names.add(normalized)
            if name and normalized in EXCLUDED_ICE_CREAM_NAMES:
                excluded_ice_cream_rows += 1
                reviews.append(ImportRowReview(
                    source_row, name, {}, "excluded", "Ice cream rows are not imported."
                ))
                continue
            nutrients: dict[str, Decimal] = {}
            shown: dict[str, str] = {}
            row_errors: list[str] = []
            correction_fields: list[str] = []
            if not name:
                correction_fields.append("food_name")
                row_errors.append(f"Row {source_row}: food name is blank.")
            for field in NUTRIENT_FIELDS:
                if field not in positions:
                    nutrients[field] = ZERO
                    continue
                position = positions[field]
                raw = values[position].strip() if len(values) > position else ""
                if not raw and field not in ("calories", "protein", "fat", "carbohydrates"):
                    nutrients[field] = ZERO
                    continue
                shown[field] = raw
                try:
                    value = parse_decimal(raw)
                    if not value.is_finite() or value < ZERO:
                        raise InvalidOperation
                    nutrients[field] = value
                except (InvalidOperation, ValueError):
                    nutrients[field] = ZERO
                    correction_fields.append(field)
                    row_errors.append(
                        f"Row {source_row} ({name or 'unnamed food'}): enter a non-negative number in {header[position]}"
                        + (" (required)." if field in ("calories", "protein", "fat", "carbohydrates") else ".")
                    )
            basis = BASIS_GRAMS
            if "basis" in positions:
                position = positions["basis"]
                raw_basis = values[position].strip() if len(values) > position else ""
                parsed_basis = parse_basis(raw_basis)
                if parsed_basis is None:
                    correction_fields.append("basis")
                    row_errors.append(
                        f"Row {source_row} ({name or 'unnamed food'}): “{raw_basis}” is not a basis; "
                        "use g (per 100 g) or count (per item)."
                    )
                else:
                    basis = parsed_basis
                shown["basis"] = "item" if basis == BASIS_COUNT else "100 g"
            if row_errors:
                numeric_errors = [error for error in row_errors if "enter a non-negative number" in error]
            else:
                numeric_errors = []
            if numeric_errors:
                malformed += 1
                errors.extend(numeric_errors)
            source_key = (
                "csv:food:" + normalized if name else f"csv:food:row:{source_row}"
            )
            stable_id = str(uuid.uuid5(uuid.NAMESPACE_URL, source_key))
            imported_food = Food(stable_id, name, Nutrients.from_mapping(nutrients), True, basis)
            if correction_fields:
                invalid_foods.append(InvalidImportFood(
                    imported_food, source_key, source_row, tuple(correction_fields), tuple(row_errors)
                ))
                reviews.append(ImportRowReview(
                    source_row, name, shown, "needs_correction",
                    " ".join(row_errors).replace(f"Row {source_row}: ", "").replace(
                        f"Row {source_row} ({name or 'unnamed food'}): ", ""
                    ),
                ))
            else:
                foods.append(ImportFood(imported_food, source_key, source_row))
                reviews.append(ImportRowReview(source_row, name, shown, "ready"))
        report = ImportReport(
            rows_read, len(foods), duplicates, blank_names, malformed,
            excluded_ice_cream_rows, ignored, tuple(errors)
        )
        return ImportPreview(
            tuple(foods), report, tuple(invalid_foods), tuple(reviews),
            analysis.matches, header_index + 1, table.delimiter,
        )

    @staticmethod
    def _find_header(rows: list[list[str]]):
        required = set(FOOD_REQUIRED_FIELDS)
        for index, row in enumerate(rows[:50]):
            analysis = analyze_headers(row, FOOD_FIELD_ALIASES)
            available = set(analysis.positions) | set(analysis.duplicates)
            if not required.issubset(available):
                continue
            if analysis.duplicates:
                duplicate_labels = ", ".join(FIELD_LABELS.get(field, field) for field in analysis.duplicates)
                raise ImportFormatError(
                    "The food CSV contains duplicate headers for the same field: "
                    + duplicate_labels + ".\n\n" + FOOD_CSV_FORMAT_GUIDANCE,
                    header_issues(rows, FOOD_FIELD_ALIASES, FOOD_REQUIRED_FIELDS, FIELD_LABELS),
                )
            return index, analysis
        closest = describe_closest_header(rows, FOOD_FIELD_ALIASES, FOOD_REQUIRED_FIELDS)
        raise ImportFormatError(
            "Could not find a food catalogue header with all required fields within the first 50 rows. "
            + (closest + " " if closest else "") + FOOD_CSV_FORMAT_GUIDANCE,
            header_issues(rows, FOOD_FIELD_ALIASES, FOOD_REQUIRED_FIELDS, FIELD_LABELS),
        )

    def apply(self, preview: ImportPreview) -> ImportResult:
        imported, already_present, name_conflicts = self.repository.seed_foods(tuple(
            (entry.food, entry.source_key, entry.source_row) for entry in preview.foods
        ))
        return ImportResult(imported, already_present, name_conflicts)
