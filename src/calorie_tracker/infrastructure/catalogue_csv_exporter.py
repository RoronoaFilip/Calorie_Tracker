"""Write the food and recipe catalogue to spreadsheet-friendly CSV files that the app can import again."""

import csv
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path

from calorie_tracker.domain.nutrition import unit_label
from calorie_tracker.domain.recipes import Food
from .repositories import RecipeRecord

FOOD_HEADER = (
    "food_name", "basis", "calories", "fat", "saturated_fat", "carbohydrates",
    "sugars", "protein", "fiber", "omega_3", "omega_6",
)
RECIPE_HEADER = ("recipe_name", "yield_g", "ingredient", "amount", "unit")


def _number(value: Decimal) -> str:
    text = f"{value.normalize():f}"
    return "0" if text in ("-0", "") else text


def export_foods_csv(foods: Iterable[Food], path: Path | str) -> int:
    """One row per food. ``basis`` is ``g`` (nutrients per 100 g) or ``count`` (nutrients per item)."""
    count = 0
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(FOOD_HEADER)
        for food in foods:
            nutrients = food.nutrients_per_100g
            writer.writerow((
                food.name, food.basis,
                *(_number(getattr(nutrients, field)) for field in FOOD_HEADER[2:]),
            ))
            count += 1
    return count


def export_recipes_csv(recipes: Iterable[RecipeRecord], path: Path | str) -> int:
    """One row per ingredient; the recipe name and final yield repeat on each of its rows.

    Ingredients are referenced by food name, so import the foods first on a new computer.
    Returns the number of recipes written.
    """
    count = 0
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(RECIPE_HEADER)
        for record in recipes:
            for ingredient in record.draft.ingredients:
                writer.writerow((
                    record.draft.name, _number(record.draft.yield_g), ingredient.food.name,
                    _number(ingredient.amount_g), unit_label(ingredient.food.basis),
                ))
            count += 1
    return count
