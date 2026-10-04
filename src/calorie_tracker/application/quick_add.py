"""Turn the rows of the Quick add table into the rows of a diary CSV table.

The table is then checked by the normal diary import, so unknown foods, bad amounts and missing meals are
shown on the same review screen as a CSV import. Nobody has to write a CSV by hand.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

QUICK_ADD_HEADER = ["food_name", "grams_eaten", "meal"]


def format_quick_amount(amount: Decimal | float | str) -> str:
    """100.0 -> '100', 0.5 -> '0.5' (plain digits the CSV importer always reads)."""
    value = Decimal(str(amount))
    return f"{value.normalize():f}" if value else "0"


def quick_add_rows(entries: Iterable[tuple[str, Decimal | float | str, str]]) -> list[list[str]]:
    """Header row plus one [food_name, amount, meal] row per (food, amount, meal); rows without a food are dropped."""
    rows = [QUICK_ADD_HEADER[:]]
    for food, amount, meal in entries:
        if food.strip():
            rows.append([food.strip(), format_quick_amount(amount), meal])
    return rows
