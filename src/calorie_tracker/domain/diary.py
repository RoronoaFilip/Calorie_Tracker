from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from .nutrition import BASIS_GRAMS, Nutrients, unit_label

MEALS = ("Breakfast", "Lunch", "Dinner", "Snacks")


@dataclass(frozen=True)
class DiaryEntry:
    id: str
    diary_date: str
    meal: str
    catalogue_item_id: str | None
    display_name: str
    amount_g: Decimal  # grams, or a number of items when ``basis`` is "count"
    nutrients_per_100g: Nutrients  # snapshot: per 100 g, or per item when ``basis`` is "count"
    basis: str = BASIS_GRAMS

    @property
    def nutrients(self) -> Nutrients:
        return self.nutrients_per_100g.for_quantity(self.amount_g, self.basis)

    @property
    def unit(self) -> str:
        return unit_label(self.basis)


@dataclass(frozen=True)
class DayTotals:
    meals: dict[str, Nutrients]
    total: Nutrients


@dataclass(frozen=True)
class MealPortion:
    meal: str
    amount_g: Decimal


_SPLIT_TOLERANCE = Decimal("0.005")


def normalize_portions(
    total_g: Decimal, portions: Iterable[tuple[str, Decimal]], unit: str = "g"
) -> tuple[MealPortion, ...]:
    """Validate a split of one amount across meals and return one portion per meal.

    Zero amounts are dropped, repeated meals are merged, and a rounding gap of at most
    0.005 is absorbed by the largest portion so the parts add up exactly to the total.
    """
    merged: dict[str, Decimal] = {}
    for meal, amount in portions:
        if meal not in MEALS:
            raise ValueError(f"Meal must be one of: {', '.join(MEALS)}.")
        if not amount.is_finite() or amount < 0:
            raise ValueError("Portion amounts must be zero or greater.")
        if amount > 0:
            merged[meal] = merged.get(meal, Decimal(0)) + amount
    if not merged:
        raise ValueError(f"Give at least one meal a portion greater than 0 {unit}.")
    difference = total_g - sum(merged.values())
    if abs(difference) > _SPLIT_TOLERANCE:
        raise ValueError(
            f"The portions add up to {sum(merged.values()):f} {unit} but the total is {total_g:f} {unit}."
        )
    largest = max(merged, key=lambda meal: merged[meal])
    merged[largest] += difference
    return tuple(MealPortion(meal, merged[meal]) for meal in MEALS if meal in merged)
