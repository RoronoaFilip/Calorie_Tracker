"""Read recipes from a CSV with one row per ingredient (the format the recipe export writes).

Ingredients are matched by name to active basic foods in the catalogue. Recipes whose name already exists are
reported and skipped, so an import never overwrites anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from calorie_tracker.domain.food_matching import FoodName, suggest_foods
from calorie_tracker.domain.nutrition import ZERO, unit_label
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient, preview_recipe
from .csv_headers import FIELD_LABELS, RECIPE_FIELD_ALIASES, ColumnMatch, analyze_headers, describe_closest_header
from .csv_issues import CsvIssue, header_issues
from .csv_reading import CsvReadError, CsvTable, parse_decimal, read_csv_rows, read_csv_text
from .repositories import FoodRepository, RecipeRepository

REQUIRED_FIELDS = ("recipe_name", "ingredient", "amount")
FORMAT_GUIDANCE = (
    "\n\nExpected header: recipe_name,yield_g,ingredient,amount\n"
    "Example rows:\nPancakes,300,Oats,100\nPancakes,300,Egg,2\n"
    "One row per ingredient; the recipe name (and final yield) can be left empty on the following rows of the "
    "same recipe. Amounts are grams, or a number of items for foods counted per item. The final yield is "
    "optional when every ingredient is weighed in grams."
)

STATUS_READY, STATUS_EXISTS, STATUS_PROBLEM = "ready", "exists", "problem"


class RecipeCsvFormatError(ValueError):
    """The CSV lacks the columns needed for a recipe import (``issues`` pin it to cells for the repair screen)."""

    def __init__(self, message: str, issues: tuple[CsvIssue, ...] = (), table: CsvTable | None = None):
        super().__init__(message)
        self.issues = issues
        self.table = table


@dataclass(frozen=True)
class RecipeImportItem:
    """One recipe found in the file, with what will happen to it."""

    name: str
    source_rows: tuple[int, ...]
    ingredient_count: int
    status: str
    message: str = ""
    draft: RecipeDraft | None = None

    @property
    def is_ready(self) -> bool:
        return self.status == STATUS_READY and self.draft is not None


@dataclass(frozen=True)
class RecipeCsvPreview:
    items: tuple[RecipeImportItem, ...]
    column_matches: tuple[ColumnMatch, ...] = ()
    ignored_headers: tuple[str, ...] = ()
    header_row: int = 1
    delimiter: str = ","

    @property
    def ready(self) -> tuple[RecipeImportItem, ...]:
        return tuple(item for item in self.items if item.is_ready)


@dataclass(frozen=True)
class _Line:
    row: int  # 0-based table row
    recipe: str
    ingredient: str
    amount: Decimal | None
    yield_g: Decimal | None
    food: Food | None
    problems: tuple[tuple[str, str], ...]  # (field, message)


def _key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


class CsvRecipeImporter:
    def __init__(self, foods: FoodRepository, recipes: RecipeRepository):
        self.foods = foods
        self.recipes = recipes

    def read(self, path: Path | str) -> CsvTable:
        try:
            return read_csv_rows(path)
        except (OSError, CsvReadError) as error:
            raise RecipeCsvFormatError(f"Could not read this CSV file: {error}{FORMAT_GUIDANCE}") from error

    def read_text(self, text: str) -> CsvTable:
        """The same as ``read`` for CSV text that was pasted instead of chosen as a file."""
        try:
            return read_csv_text(text)
        except CsvReadError as error:
            raise RecipeCsvFormatError(f"Could not read this CSV text: {error}{FORMAT_GUIDANCE}") from error

    def preview(self, path: Path | str) -> RecipeCsvPreview:
        return self.preview_table(self.read(path))

    # ---- parsing -------------------------------------------------------------------------------------

    @staticmethod
    def _find_header(rows: list[list[str]]):
        for index, row in enumerate(rows[:50]):
            analysis = analyze_headers(row, RECIPE_FIELD_ALIASES)
            available = set(analysis.positions) | set(analysis.duplicates)
            if not set(REQUIRED_FIELDS).issubset(available):
                continue
            if analysis.duplicates:
                labels = ", ".join(FIELD_LABELS.get(field, field) for field in analysis.duplicates)
                raise RecipeCsvFormatError(
                    f"The CSV contains duplicate headers for the same field: {labels}.{FORMAT_GUIDANCE}",
                    header_issues(rows, RECIPE_FIELD_ALIASES, REQUIRED_FIELDS, FIELD_LABELS),
                )
            return index, analysis
        closest = describe_closest_header(rows, RECIPE_FIELD_ALIASES, REQUIRED_FIELDS)
        raise RecipeCsvFormatError(
            "This file is not in the recipe import format. It needs recipe name, ingredient and amount columns."
            + (f"\n\n{closest}" if closest else "") + FORMAT_GUIDANCE,
            header_issues(rows, RECIPE_FIELD_ALIASES, REQUIRED_FIELDS, FIELD_LABELS),
        )

    def _parse_lines(self, table: CsvTable):
        rows = table.rows
        try:
            header_index, analysis = self._find_header(rows)
        except RecipeCsvFormatError as error:
            error.table = table
            raise
        columns = analysis.positions
        foods_by_name: dict[str, list[Food]] = {}
        catalogue: list[FoodName] = []
        for food in self.foods.search(""):
            if food.active:
                foods_by_name.setdefault(_key(food.name), []).append(food)
                catalogue.append(FoodName(food.id, food.name))
        lines: list[_Line] = []
        current = ""
        for index in range(header_index + 1, len(rows)):
            values = rows[index]
            if not any(value.strip() for value in values):
                continue

            def get(field: str) -> str:
                column = columns.get(field)
                return values[column].strip() if column is not None and column < len(values) else ""

            problems: list[tuple[str, str]] = []
            name = re.sub(r"\s+", " ", get("recipe_name"))
            if name:
                current = name
            elif current:
                name = current  # spreadsheet style: the name is only written on the first row
            else:
                problems.append(("recipe_name", "Recipe name is blank."))

            ingredient = re.sub(r"\s+", " ", get("ingredient"))
            food: Food | None = None
            if not ingredient:
                problems.append(("ingredient", "Ingredient is blank."))
            else:
                matches = foods_by_name.get(_key(ingredient), [])
                if len(matches) == 1:
                    food = matches[0]
                elif len(matches) > 1:
                    problems.append(("ingredient", f"Several foods are named '{ingredient}'; rename the duplicates first."))
                else:
                    message = f"Food '{ingredient}' was not found in your foods."
                    suggestions = suggest_foods(ingredient, catalogue)
                    if suggestions:
                        message += f" Did you mean '{suggestions[0].name}'?"
                        if len(suggestions) > 1:
                            message += " Other possibilities: " + ", ".join(f"'{item.name}'" for item in suggestions[1:]) + "."
                    problems.append(("ingredient", message))

            amount: Decimal | None = None
            amount_text = get("amount")
            try:
                amount = parse_decimal(amount_text)
                if not amount.is_finite() or amount <= ZERO:
                    amount = None
                    raise ValueError
            except (InvalidOperation, ValueError):
                unit = unit_label(food.basis) if food else "g"
                problems.append(("amount", (
                    f"Amount '{amount_text}' is not a number; use a number greater than 0 ({unit})."
                    if amount_text else f"Amount is empty; enter a number greater than 0 ({unit})."
                )))

            yield_g: Decimal | None = None
            yield_text = get("yield_g")
            if yield_text:
                try:
                    yield_g = parse_decimal(yield_text)
                    if not yield_g.is_finite() or yield_g <= ZERO:
                        yield_g = None
                        raise ValueError
                except (InvalidOperation, ValueError):
                    problems.append(("yield_g", f"Final yield '{yield_text}' must be a number of grams greater than 0."))
            lines.append(_Line(index, name, ingredient, amount, yield_g, food, tuple(problems)))
        return header_index, analysis, columns, lines

    def issues_for(self, table: CsvTable) -> tuple[CsvIssue, ...]:
        """Bad values as cell positions. A recipe is all-or-nothing, so its other rows are marked too."""
        try:
            _, _, columns, lines = self._parse_lines(table)
        except RecipeCsvFormatError as error:
            return error.issues or (CsvIssue(0, None, str(error)),)
        broken = {_key(line.recipe) for line in lines if line.problems and line.recipe}
        issues: list[CsvIssue] = []
        for line in lines:
            for field, message in line.problems:
                column = columns.get(field)
                issues.append(CsvIssue(line.row, column if column is not None else columns["recipe_name"], message))
            if not line.problems and _key(line.recipe) in broken:
                issues.append(CsvIssue(
                    line.row, columns["recipe_name"],
                    f"Another row of “{line.recipe}” has a problem. Fix it, or skip all rows of this recipe.",
                ))
        return tuple(issues)

    def preview_table(self, table: CsvTable) -> RecipeCsvPreview:
        header_index, analysis, _columns, lines = self._parse_lines(table)
        groups: dict[str, list[_Line]] = {}
        for line in lines:
            groups.setdefault(_key(line.recipe), []).append(line)
        items: list[RecipeImportItem] = []
        for group in groups.values():
            name = group[0].recipe
            rows = tuple(line.row + 1 for line in group)
            problems = [message for line in group for _, message in line.problems]
            if problems:
                items.append(RecipeImportItem(name, rows, len(group), STATUS_PROBLEM, " ".join(problems)))
                continue
            if self.recipes.name_exists(name):
                items.append(RecipeImportItem(
                    name, rows, len(group), STATUS_EXISTS,
                    "A recipe with this name already exists; it is left unchanged.",
                ))
                continue
            ingredients = tuple(RecipeIngredient(line.food, line.amount) for line in group)
            yield_g = next((line.yield_g for line in group if line.yield_g is not None), None)
            weighed = sum((item.amount_g for item in ingredients if not item.food.is_counted), ZERO)
            if yield_g is None:
                if any(item.food.is_counted for item in ingredients):
                    items.append(RecipeImportItem(
                        name, rows, len(group), STATUS_PROBLEM,
                        "Counted ingredients have no weight, so this recipe needs a final yield (yield_g).",
                    ))
                    continue
                yield_g = weighed
            draft = RecipeDraft(name, yield_g, ingredients)
            check = preview_recipe(draft)
            if check.errors:
                items.append(RecipeImportItem(
                    name, rows, len(group), STATUS_PROBLEM, " ".join(error.message for error in check.errors)
                ))
                continue
            note = " ".join(warning.message for warning in check.warnings)
            items.append(RecipeImportItem(name, rows, len(group), STATUS_READY, note, draft))
        return RecipeCsvPreview(
            tuple(items), analysis.matches, analysis.ignored, header_index + 1, table.delimiter
        )
