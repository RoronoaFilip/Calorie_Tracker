"""Explicit, context-aware CSV header aliases used by the import adapters."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence


def normalize_header(value: str) -> str:
    """Case-fold a header and remove spacing and punctuation for alias matching."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", without_marks)


FOOD_FIELD_ALIASES: Mapping[str, tuple[str, ...]] = {
    "food_name": ("food_name", "food name", "name", "product"),
    "calories": ("calories", "kcal", "calories / 100g"),
    "protein": ("protein", "protein / 100g"),
    "fat": ("fat", "fat / 100g"),
    "carbohydrates": (
        "carbs", "carbohydrates", "carbs / 100g", "carbohydrates / 100g",
    ),
    "fiber": ("fiber", "dietary fiber", "fiber / 100g"),
    "saturated_fat": ("saturated_fat", "saturated fat / 100g"),
    "sugars": ("sugars", "sugars / 100g"),
    "omega_3": ("omega-3", "omega-3 / 100g"),
    "omega_6": ("omega-6", "omega-6 / 100g"),
}

DIARY_FIELD_ALIASES: Mapping[str, tuple[str, ...]] = {
    "food_name": FOOD_FIELD_ALIASES["food_name"],
    "amount_g": ("grams_eaten (all meals)", "amount", "amount_g", "grams", "quantity"),
    "meal": ("meal", "time", "meal_time"),
}


def match_headers(
    headers: Sequence[str], aliases: Mapping[str, Sequence[str]]
) -> tuple[dict[str, int], tuple[str, ...], tuple[str, ...]]:
    """Return field positions, duplicate logical fields, and ignored headers."""
    normalized_aliases = {
        field: {normalize_header(alias) for alias in names}
        for field, names in aliases.items()
    }
    positions: dict[str, int] = {}
    duplicates: list[str] = []
    ignored: list[str] = []
    for index, original in enumerate(headers):
        normalized = normalize_header(original)
        field = next(
            (name for name, accepted in normalized_aliases.items() if normalized in accepted),
            None,
        )
        if field is None:
            ignored.append(original)
            continue
        if field in positions:
            if field not in duplicates:
                duplicates.append(field)
        else:
            positions[field] = index
    return positions, tuple(duplicates), tuple(ignored)
