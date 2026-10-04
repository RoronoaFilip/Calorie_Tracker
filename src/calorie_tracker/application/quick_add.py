"""Turn a few typed lines such as 'Oats 45 breakfast' into the rows of a diary CSV table.

The table is then checked by the normal diary import, so unknown foods, bad amounts and missing meals are
shown on the same review screen as a CSV import.
"""

from __future__ import annotations

import csv
import io
import re
from decimal import Decimal, InvalidOperation

QUICK_ADD_HEADER = ["food_name", "grams_eaten", "meal"]

_MEAL_WORDS = (
    "breakfast", "lunch", "dinner", "snack", "snacks", "supper", "morning", "noon", "midday", "evening",
)
_NUMBER = r"\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?"
_UNIT = r"g|gr|gram|grams|x|pc|pcs|piece|pieces|item|items|count"
_NAME_FIRST = re.compile(
    rf"^\s*(?P<name>.+?)\s+(?P<amount>{_NUMBER})\s*(?P<unit>{_UNIT})?\s*(?P<meal>[^\W\d_]+)?\s*$",
    re.IGNORECASE,
)
_AMOUNT_FIRST = re.compile(
    rf"^\s*(?P<amount>{_NUMBER})\s*(?P<unit>{_UNIT})?\s+(?P<name>.+?)(?:\s+(?P<meal>{'|'.join(_MEAL_WORDS)}))?\s*$",
    re.IGNORECASE,
)


def normalize_quick_amount(text: str) -> str:
    """'1/2' -> '0.5', '1 1/2' -> '1.5', '45,5' -> '45,5' (decimals are left for the importer to read)."""
    text = text.strip()
    mixed = re.fullmatch(r"(\d+)\s+(\d+)/(\d+)", text)
    simple = re.fullmatch(r"(\d+)/(\d+)", text)
    try:
        if mixed:
            whole, top, bottom = (Decimal(part) for part in mixed.groups())
            value = whole + top / bottom
        elif simple:
            top, bottom = (Decimal(part) for part in simple.groups())
            value = top / bottom
        else:
            return text
    except (InvalidOperation, ZeroDivisionError):
        return text
    return f"{value.quantize(Decimal('0.0001')).normalize():f}"


def parse_quick_line(line: str, default_meal: str = "") -> list[str]:
    """One typed line -> [food_name, amount, meal]. Lines that cannot be understood keep their text as the name."""
    text = line.strip()
    for pattern in (_NAME_FIRST, _AMOUNT_FIRST):
        match = pattern.fullmatch(text)
        if match is None:
            continue
        # A last word that is no known meal is kept as typed, so the review screen flags it.
        meal = match.group("meal") or ""
        return [match.group("name").strip(" ,;"), normalize_quick_amount(match.group("amount")), meal or default_meal]
    for delimiter in ("\t", ";", ","):
        if delimiter in text:
            cells = next(csv.reader(io.StringIO(text), delimiter=delimiter))
            cells = [cell.strip() for cell in cells] + ["", "", ""]
            return [cells[0], normalize_quick_amount(cells[1]), cells[2] or default_meal]
    return [text, "", default_meal]


def quick_add_rows(text: str, default_meal: str = "") -> list[list[str]]:
    """Header row plus one row per non-empty typed line."""
    rows = [QUICK_ADD_HEADER[:]]
    rows.extend(parse_quick_line(line, default_meal) for line in text.splitlines() if line.strip())
    return rows
