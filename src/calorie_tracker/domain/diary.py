from dataclasses import dataclass
from decimal import Decimal

from .nutrition import Nutrients


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
