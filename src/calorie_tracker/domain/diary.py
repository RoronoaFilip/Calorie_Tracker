from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from .nutrition import Nutrients

MEALS = ("Breakfast", "Lunch", "Dinner", "Snacks")


@dataclass(frozen=True)
class DiaryEntry:
    id: str
    diary_date: str
    meal: str
    catalogue_item_id: str | None
    display_name: str
    amount_g: Decimal
    nutrients_per_100g: Nutrients

    @property
    def nutrients(self) -> Nutrients:
        return self.nutrients_per_100g.for_amount(self.amount_g)


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
    total_g: Decimal, portions: Iterable[tuple[str, Decimal]]
) -> tuple[MealPortion, ...]:
    """Validate a split of one amount across meals and return one portion per meal.

    Zero amounts are dropped, repeated meals are merged, and a rounding gap of at most
    0.005 g is absorbed by the largest portion so the parts add up exactly to the total.
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
        raise ValueError("Give at least one meal a portion greater than 0 g.")
    difference = total_g - sum(merged.values())
    if abs(difference) > _SPLIT_TOLERANCE:
        raise ValueError(
            f"The portions add up to {sum(merged.values()):f} g but the total is {total_g:f} g."
        )
    largest = max(merged, key=lambda meal: merged[meal])
    merged[largest] += difference
    return tuple(MealPortion(meal, merged[meal]) for meal in MEALS if meal in merged)
