"""Explicit, forgiving CSV header matching used by the import adapters."""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def normalize_header(value: str) -> str:
    """Case-fold a header and remove spacing and punctuation for alias matching."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", without_marks)


FOOD_FIELD_ALIASES: Mapping[str, tuple[str, ...]] = {
    "food_name": ("food_name", "food name", "name", "product", "food", "food item", "item"),
    "calories": ("calories", "calorie", "kcal", "energy", "calories / 100g"),
    "protein": ("protein", "proteins", "protein / 100g"),
    "fat": ("fat", "fats", "fat / 100g"),
    "carbohydrates": (
        "carbs", "carb", "carbohydrates", "carbohydrate", "carbs / 100g", "carbohydrates / 100g",
    ),
    "fiber": ("fiber", "fibre", "dietary fiber", "dietary fibre", "fiber / 100g"),
    "saturated_fat": ("saturated_fat", "saturated fat", "saturates", "saturated fat / 100g"),
    "sugars": ("sugars", "sugar", "sugars / 100g"),
    "omega_3": ("omega-3", "omega 3", "omega-3 / 100g"),
    "omega_6": ("omega-6", "omega 6", "omega-6 / 100g"),
    # Optional: "g" (values are per 100 g, the default) or "count" (values are per single item).
    "basis": ("basis", "per", "unit basis", "nutrients per", "serving basis"),
}

RECIPE_FIELD_ALIASES: Mapping[str, tuple[str, ...]] = {
    "recipe_name": ("recipe_name", "recipe name", "recipe", "dish", "name"),
    "ingredient": (
        "ingredient", "ingredient name", "ingredient_name", "food", "food name", "food_name", "item",
    ),
    "amount": ("amount", "amount_g", "amount (g)", "quantity", "qty", "grams", "grams_eaten", "weight"),
    "yield_g": ("yield_g", "yield", "final yield", "yield (g)", "total weight", "final weight"),
}

DIARY_FIELD_ALIASES: Mapping[str, tuple[str, ...]] = {
    "food_name": FOOD_FIELD_ALIASES["food_name"],
    "amount_g": (
        "grams_eaten", "grams eaten", "grams", "gram", "g", "amount", "amount_g", "amount (g)",
        "quantity", "weight", "grams_eaten (all meals)",
    ),
    "meal": ("meal", "time", "meal_time", "meal time", "meal type"),
}

FIELD_LABELS: Mapping[str, str] = {
    "food_name": "Food name", "amount_g": "Amount (g)", "meal": "Meal",
    "recipe_name": "Recipe name", "ingredient": "Ingredient", "amount": "Amount", "yield_g": "Final yield (g)",
    "basis": "Per (g or count)",
    "calories": "Calories", "protein": "Protein", "fat": "Fat", "carbohydrates": "Carbohydrates",
    "fiber": "Fiber", "saturated_fat": "Saturated fat", "sugars": "Sugars",
    "omega_3": "Omega-3", "omega_6": "Omega-6",
}

_UNIT_SUFFIXES = ("per100grams", "per100gr", "per100g", "100grams", "100gr", "100g", "kcal", "grams", "gram", "gr", "g")
_PARENTHETICAL = re.compile(r"[\(\[].*?[\)\]]")
_EXACT, _CLEANED, _APPROXIMATE = 0, 1, 2
_MATCH_LABELS = {_EXACT: "exact", _CLEANED: "cleaned", _APPROXIMATE: "approximate"}


@dataclass(frozen=True)
class ColumnMatch:
    field: str
    header: str
    column: int
    how: str  # "exact", "cleaned" or "approximate"


@dataclass(frozen=True)
class HeaderAnalysis:
    positions: dict[str, int]
    duplicates: tuple[str, ...]
    ignored: tuple[str, ...]
    matches: tuple[ColumnMatch, ...]


def _strip_units(key: str) -> str:
    changed = True
    while changed and key:
        changed = False
        for suffix in _UNIT_SUFFIXES:
            if key.endswith(suffix) and len(key) > len(suffix):
                key = key[: -len(suffix)]
                changed = True
                break
    return key


def _candidate_keys(header: str) -> tuple[str, str]:
    plain = normalize_header(header)
    cleaned = _strip_units(normalize_header(_PARENTHETICAL.sub(" ", header)))
    return plain, cleaned


def analyze_headers(headers: Sequence[str], aliases: Mapping[str, Sequence[str]]) -> HeaderAnalysis:
    """Match headers to logical fields: exact alias, alias after removing '(…)'/units, then typos."""
    accepted = {
        field: {normalize_header(alias) for alias in names} for field, names in aliases.items()
    }
    every_alias = sorted({alias for names in accepted.values() for alias in names})
    owner = {alias: field for field, names in accepted.items() for alias in names}
    candidates: dict[str, list[tuple[int, int]]] = {}
    ignored: list[str] = []
    for index, original in enumerate(headers):
        plain, cleaned = _candidate_keys(original)
        field, rank = None, _EXACT
        if plain in owner:
            field = owner[plain]
        elif cleaned in owner:
            field, rank = owner[cleaned], _CLEANED
        elif len(cleaned) >= 5 and "total" not in cleaned:
            close = [
                alias for alias in difflib.get_close_matches(cleaned, every_alias, n=1, cutoff=0.84)
                if abs(len(alias) - len(cleaned)) <= 2
            ]
            if close:
                field, rank = owner[close[0]], _APPROXIMATE
        if field is None:
            ignored.append(original)
        else:
            candidates.setdefault(field, []).append((rank, index))
    positions: dict[str, int] = {}
    duplicates: list[str] = []
    matches: list[ColumnMatch] = []
    for field, found in candidates.items():
        best = min(rank for rank, _ in found)
        winners = [index for rank, index in found if rank == best]
        positions[field] = winners[0]
        if len(winners) > 1:
            duplicates.append(field)
        for rank, index in found:
            if index == winners[0]:
                matches.append(ColumnMatch(field, headers[index], index, _MATCH_LABELS[rank]))
            else:
                ignored.append(headers[index])
    matches.sort(key=lambda match: match.column)
    return HeaderAnalysis(positions, tuple(duplicates), tuple(ignored), tuple(matches))


def match_headers(
    headers: Sequence[str], aliases: Mapping[str, Sequence[str]]
) -> tuple[dict[str, int], tuple[str, ...], tuple[str, ...]]:
    """Return field positions, duplicate logical fields, and ignored headers."""
    analysis = analyze_headers(headers, aliases)
    return analysis.positions, analysis.duplicates, analysis.ignored


def describe_closest_header(
    rows: Sequence[Sequence[str]], aliases: Mapping[str, Sequence[str]], required: Sequence[str]
) -> str:
    """Explain which required columns the best-looking header row has and lacks."""
    best_index, best_found = -1, -1
    for index, row in enumerate(rows[:50]):
        found = sum(field in analyze_headers(row, aliases).positions for field in required)
        if found > best_found:
            best_index, best_found = index, found
    if best_index < 0 or best_found <= 0:
        return ""
    analysis = analyze_headers(rows[best_index], aliases)
    parts = [
        f"{FIELD_LABELS.get(field, field)} {'found' if field in analysis.positions else 'MISSING'}"
        for field in required
    ]
    seen = ", ".join(f"'{value}'" for value in rows[best_index] if value.strip())
    return f"Closest header (row {best_index + 1}): {'; '.join(parts)}. Columns seen: {seen}."
