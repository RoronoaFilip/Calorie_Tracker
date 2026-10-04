import difflib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from calorie_tracker.domain.diary import MEALS
from calorie_tracker.infrastructure.csv_headers import (
    DIARY_FIELD_ALIASES,
    ColumnMatch,
    analyze_headers,
    describe_closest_header,
)
from calorie_tracker.infrastructure.csv_issues import CsvIssue, header_issues
from calorie_tracker.infrastructure.csv_reading import CsvReadError, CsvTable, parse_decimal, read_csv_rows, read_csv_text
from calorie_tracker.infrastructure.repositories import FoodRepository


FOOD_NAME_HEADER = "food_name"
AMOUNT_HEADER = "grams_eaten"
MEAL_HEADER = "meal"
FORMAT_GUIDANCE = (
    f"\n\nExpected header: {FOOD_NAME_HEADER},{AMOUNT_HEADER},{MEAL_HEADER}\n"
    "Example row: Oats,45.5,Breakfast\n"
    "The amount column may also be called 'grams eaten', 'grams', 'amount' or 'quantity'. "
    "Amounts are in grams (or a number of items for foods counted per item). The meal column is optional; if omitted, choose a meal for each valid row."
)

_MEAL_WORDS = {
    **{meal.casefold(): meal for meal in MEALS},
    "snack": "Snacks", "supper": "Dinner", "evening": "Dinner",
    "morning": "Breakfast", "noon": "Lunch", "midday": "Lunch",
}


_DIARY_LABELS = {"food_name": "Food name", "amount_g": "Amount (g)", "meal": "Meal"}


class DiaryCsvFormatError(ValueError):
    """The selected CSV does not contain the columns needed for diary import.

    ``issues`` pin the problem to cells and ``table`` holds the rows that were read (when the file could be
    read at all), so a repair screen can let the user fix them in memory.
    """

    def __init__(self, message: str, issues: tuple[CsvIssue, ...] = (), table: CsvTable | None = None):
        super().__init__(message)
        self.issues = issues
        self.table = table


@dataclass(frozen=True)
class DiaryCsvRow:
    source_row: int
    food_name: str
    amount_g: Decimal | None
    meal: str | None
    catalogue_item_id: str | None
    error: str | None = None
    # (field, message) for bad *values* (blank name, unusable amount or meal) as opposed to catalogue matching
    # problems; the CSV repair screen is shown for these.
    value_problems: tuple[tuple[str, str], ...] = ()
    basis: str = "g"  # of the matched food: the amount is grams ("g") or a number of items ("count")

    @property
    def is_importable(self) -> bool:
        return self.error is None and self.amount_g is not None and self.catalogue_item_id is not None


@dataclass(frozen=True)
class DiaryCsvPreview:
    rows: tuple[DiaryCsvRow, ...]
    column_matches: tuple[ColumnMatch, ...] = ()
    ignored_headers: tuple[str, ...] = ()
    header_row: int = 1
    delimiter: str = ","

    @property
    def importable_count(self) -> int:
        return sum(row.is_importable for row in self.rows)

    @property
    def skipped_rows(self) -> tuple[DiaryCsvRow, ...]:
        return tuple(row for row in self.rows if not row.is_importable)

    @property
    def needs_meal_assignment(self) -> tuple[DiaryCsvRow, ...]:
        return tuple(row for row in self.rows if row.is_importable and row.meal is None)


def _name_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


class CsvDiaryImporter:
    """Reads meal quantities from CSV and matches names to active catalogue foods."""

    def __init__(self, foods: FoodRepository):
        self.foods = foods

    def read(self, path: Path | str) -> CsvTable:
        try:
            return read_csv_rows(path)
        except (OSError, CsvReadError) as error:
            raise DiaryCsvFormatError(f"Could not validate this CSV file: {error}{FORMAT_GUIDANCE}") from error

    def read_text(self, text: str) -> CsvTable:
        """The same as ``read`` for CSV text that was pasted instead of chosen as a file."""
        try:
            return read_csv_text(text)
        except CsvReadError as error:
            raise DiaryCsvFormatError(f"Could not validate this CSV text: {error}{FORMAT_GUIDANCE}") from error

    def preview(self, path: Path | str) -> DiaryCsvPreview:
        return self.preview_table(self.read(path))

    def issues_for(self, table: CsvTable) -> tuple[CsvIssue, ...]:
        """Missing-column and bad-value (name, amount, meal) problems in ``table`` as cell positions."""
        try:
            preview = self.preview_table(table)
        except DiaryCsvFormatError as error:
            return error.issues or (CsvIssue(0, None, str(error)),)
        positions = {match.field: match.column for match in preview.column_matches}
        return tuple(
            CsvIssue(row.source_row - 1, positions.get(field), message)
            for row in preview.rows
            for field, message in row.value_problems
        )

    def preview_table(self, table: CsvTable) -> DiaryCsvPreview:
        """Validate already-read rows. Used for the first read and again after in-memory edits."""
        rows = table.rows
        try:
            header_index, analysis = self._find_header(rows)
        except DiaryCsvFormatError as error:
            error.table = table
            raise
        columns = analysis.positions
        foods_by_name: dict[str, list[str]] = {}
        basis_by_id: dict[str, str] = {}
        display_names: dict[str, str] = {}
        for food in self.foods.search(""):
            if food.active:
                key = _name_key(food.name)
                foods_by_name.setdefault(key, []).append(food.id)
                basis_by_id[food.id] = food.basis
                display_names[key] = food.name
        parsed: list[DiaryCsvRow] = []
        for index in range(header_index + 1, len(rows)):
            values = rows[index]
            if not any(value.strip() for value in values):
                continue
            get = lambda column: values[column].strip() if column < len(values) else ""
            name = re.sub(r"\s+", " ", get(columns["food_name"]))
            amount_text = get(columns["amount_g"])
            meal_text = get(columns["meal"]) if "meal" in columns else ""
            amount: Decimal | None = None
            errors: list[str] = []
            value_problems: list[tuple[str, str]] = []

            def value_problem(field: str, message: str) -> None:
                errors.append(message)
                value_problems.append((field, message))

            if not name:
                value_problem("food_name", "Food name is blank.")
            else:
                try:
                    amount = parse_decimal(amount_text)
                    if not amount.is_finite() or amount <= 0:
                        value_problem("amount_g", "Amount must be a finite number greater than 0 g.")
                except (InvalidOperation, ValueError):
                    value_problem("amount_g", (
                        f"Amount '{amount_text}' is not a number; use grams such as 45 or 45.5."
                        if amount_text else "Amount must be a number greater than 0 g (it is empty)."
                    ))

            key = _name_key(name)
            matches = foods_by_name.get(key, []) if name else []
            food_id = matches[0] if len(matches) == 1 else None
            if name and not matches:
                message = f"Food '{name}' was not found in the active catalogue."
                close = difflib.get_close_matches(key, tuple(display_names), n=1, cutoff=0.7)
                if close:
                    message += f" Did you mean '{display_names[close[0]]}'?"
                errors.append(message)
            elif name and len(matches) > 1:
                errors.append(f"Food '{name}' has multiple active catalogue matches; resolve the duplicate names first.")

            meal: str | None = None
            if meal_text:
                meal = _MEAL_WORDS.get(meal_text.casefold())
                if meal is None:
                    value_problem("meal", f"Meal '{meal_text}' is not Breakfast, Lunch, Dinner, or Snacks.")

            parsed.append(DiaryCsvRow(
                index + 1, name, amount, meal, food_id, "; ".join(errors) if errors else None,
                tuple(value_problems), basis_by_id.get(food_id, "g") if food_id else "g",
            ))
        return DiaryCsvPreview(
            tuple(parsed), analysis.matches, analysis.ignored, header_index + 1, table.delimiter
        )

    @staticmethod
    def _find_header(rows: list[list[str]]):
        for index, row in enumerate(rows[:50]):
            analysis = analyze_headers(row, DIARY_FIELD_ALIASES)
            available = set(analysis.positions) | set(analysis.duplicates)
            if not {"food_name", "amount_g"}.issubset(available):
                continue
            if analysis.duplicates:
                duplicate_labels = ", ".join(
                    {"food_name": "food name", "amount_g": "amount", "meal": "meal/time"}.get(field, field)
                    for field in analysis.duplicates
                )
                raise DiaryCsvFormatError(
                    "The CSV contains duplicate headers for the same field: "
                    + duplicate_labels + "." + FORMAT_GUIDANCE,
                    header_issues(rows, DIARY_FIELD_ALIASES, ("food_name", "amount_g"), _DIARY_LABELS),
                )
            return index, analysis
        closest = describe_closest_header(rows, DIARY_FIELD_ALIASES, ("food_name", "amount_g"))
        raise DiaryCsvFormatError(
            "This file is not in the diary import format. It needs a food name and amount header "
            f"(for example '{FOOD_NAME_HEADER}' and '{AMOUNT_HEADER}')."
            + (f"\n\n{closest}" if closest else "") + FORMAT_GUIDANCE,
            header_issues(rows, DIARY_FIELD_ALIASES, ("food_name", "amount_g"), _DIARY_LABELS),
        )
