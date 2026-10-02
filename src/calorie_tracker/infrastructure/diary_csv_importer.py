import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from calorie_tracker.domain.diary import MEALS
from calorie_tracker.infrastructure.csv_headers import DIARY_FIELD_ALIASES, match_headers
from calorie_tracker.infrastructure.repositories import FoodRepository


FOOD_NAME_HEADER = "food_name"
AMOUNT_HEADER = "grams_eaten (all meals)"
MEAL_HEADER = "meal"
FORMAT_GUIDANCE = (
    f"\n\nExpected header: {FOOD_NAME_HEADER},{AMOUNT_HEADER},{MEAL_HEADER}\n"
    "Example row: Oats,45.5,Breakfast\n"
    "Amounts are in grams. The meal column is optional; if omitted, choose a meal for each valid row."
)


class DiaryCsvFormatError(ValueError):
    """The selected CSV does not contain the columns needed for diary import."""


@dataclass(frozen=True)
class DiaryCsvRow:
    source_row: int
    food_name: str
    amount_g: Decimal | None
    meal: str | None
    catalogue_item_id: str | None
    error: str | None = None

    @property
    def is_importable(self) -> bool:
        return self.error is None and self.amount_g is not None and self.catalogue_item_id is not None


@dataclass(frozen=True)
class DiaryCsvPreview:
    rows: tuple[DiaryCsvRow, ...]

    @property
    def importable_count(self) -> int:
        return sum(row.is_importable for row in self.rows)

    @property
    def skipped_rows(self) -> tuple[DiaryCsvRow, ...]:
        return tuple(row for row in self.rows if not row.is_importable)

    @property
    def needs_meal_assignment(self) -> tuple[DiaryCsvRow, ...]:
        return tuple(row for row in self.rows if row.is_importable and row.meal is None)


class CsvDiaryImporter:
    """Reads meal quantities from CSV and matches names to active catalogue foods."""

    def __init__(self, foods: FoodRepository):
        self.foods = foods

    def preview(self, path: Path | str) -> DiaryCsvPreview:
        try:
            with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream, strict=True))
        except (OSError, UnicodeError, csv.Error) as error:
            raise DiaryCsvFormatError(f"Could not validate this CSV file: {error}{FORMAT_GUIDANCE}") from error

        header_index, columns = self._find_header(rows)
        foods_by_name: dict[str, list[str]] = {}
        for food in self.foods.search(""):
            if food.active:
                foods_by_name.setdefault(food.name.strip().casefold(), []).append(food.id)
        parsed: list[DiaryCsvRow] = []
        for index in range(header_index + 1, len(rows)):
            values = rows[index]
            if not any(value.strip() for value in values):
                continue
            get = lambda column: values[column].strip() if column < len(values) else ""
            name = get(columns["food_name"])
            amount_text = get(columns["amount_g"])
            meal_text = get(columns["meal"]) if "meal" in columns else ""
            amount: Decimal | None = None
            errors: list[str] = []

            if not name:
                errors.append("Food name is blank.")
            else:
                try:
                    amount = Decimal(amount_text)
                    if not amount.is_finite() or amount <= 0:
                        errors.append("Amount must be a finite number greater than 0 g.")
                except (InvalidOperation, ValueError):
                    errors.append("Amount must be a number greater than 0 g.")

            matches = foods_by_name.get(name.casefold(), []) if name else []
            food_id = matches[0] if len(matches) == 1 else None
            if name and not matches:
                errors.append(f"Food '{name}' was not found in the active catalogue.")
            elif name and len(matches) > 1:
                errors.append(f"Food '{name}' has multiple active catalogue matches; resolve the duplicate names first.")

            meal: str | None = None
            if meal_text:
                meal_map = {value.casefold(): value for value in MEALS}
                meal_map["snack"] = "Snacks"
                meal = meal_map.get(meal_text.casefold())
                if meal is None:
                    errors.append(f"Meal '{meal_text}' is not Breakfast, Lunch, Dinner, or Snacks.")

            parsed.append(DiaryCsvRow(
                index + 1, name, amount, meal, food_id, "; ".join(errors) if errors else None
            ))
        return DiaryCsvPreview(tuple(parsed))

    @staticmethod
    def _find_header(rows: list[list[str]]) -> tuple[int, dict[str, int]]:
        for index, row in enumerate(rows[:50]):
            columns, duplicates, _ = match_headers(row, DIARY_FIELD_ALIASES)
            available = set(columns) | set(duplicates)
            if not {"food_name", "amount_g"}.issubset(available):
                continue
            if duplicates:
                duplicate_labels = ", ".join(
                    {"food_name": "food name", "amount_g": "amount", "meal": "meal/time"}.get(field, field)
                    for field in duplicates
                )
                raise DiaryCsvFormatError(
                    "The CSV contains duplicate headers for the same field: "
                    + duplicate_labels + "." + FORMAT_GUIDANCE
                )
            return index, columns
        raise DiaryCsvFormatError(
            "This file is not in the diary import format. It needs a food name and amount header "
            f"(for example '{FOOD_NAME_HEADER}' and '{AMOUNT_HEADER}').{FORMAT_GUIDANCE}"
        )
