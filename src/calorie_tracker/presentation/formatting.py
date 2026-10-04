"""Small text helpers shared by the views, so amounts and nutrient values read the same everywhere."""

from decimal import Decimal

from calorie_tracker.domain.diary import DiaryEntry
from calorie_tracker.domain.nutrition import BASIS_COUNT, Nutrients, unit_label


def trimmed(value: Decimal, places: int = 1) -> str:
    """'12.50' -> '12.5', '120.0' -> '120', rounded to ``places`` decimals."""
    text = f"{value:.{places}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def format_amount(amount: Decimal, basis: str) -> str:
    """'150 g' for weighed amounts, '2 pcs' / '0.5 pcs' for counted ones."""
    return f"{trimmed(amount, 3)} {unit_label(basis)}"


def format_entry_amount(entry: DiaryEntry) -> str:
    return format_amount(entry.amount_g, entry.basis)


def basis_phrase(basis: str) -> str:
    """What the nutrient values of a food refer to."""
    return "per item" if basis == BASIS_COUNT else "per 100 g"


def format_macros(nutrients: Nutrients) -> str:
    """One line with the main values, e.g. '380 kcal · Protein 13g · Carbs 60g · Fat 7g · Fiber 10g'."""
    return (
        f"{trimmed(nutrients.calories)} kcal · Protein {trimmed(nutrients.protein)}g · "
        f"Carbs {trimmed(nutrients.carbohydrates)}g · Fat {trimmed(nutrients.fat)}g · "
        f"Fiber {trimmed(nutrients.fiber)}g"
    )
