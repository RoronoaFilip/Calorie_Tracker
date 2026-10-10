from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Mapping


ZERO = Decimal("0")
HUNDRED = Decimal("100")

# What a food's nutrient values refer to: 100 g of it, or one counted item (one egg, one slice...).
BASIS_GRAMS = "g"
BASIS_COUNT = "count"
BASES = (BASIS_GRAMS, BASIS_COUNT)


def check_basis(basis: str) -> str:
    if basis not in BASES:
        raise ValueError(f"Unsupported nutrient basis: {basis!r}. Use 'g' (per 100 g) or 'count' (per item).")
    return basis


def unit_label(basis: str) -> str:
    """Short unit shown after an amount: 'g' for weighed foods, 'pcs' for counted ones."""
    return "pcs" if basis == BASIS_COUNT else "g"


@dataclass(frozen=True)
class Nutrients:
    calories: Decimal = ZERO
    fat: Decimal = ZERO
    saturated_fat: Decimal = ZERO
    carbohydrates: Decimal = ZERO
    sugars: Decimal = ZERO
    protein: Decimal = ZERO
    fiber: Decimal = ZERO
    omega_3: Decimal = ZERO
    omega_6: Decimal = ZERO

    def __add__(self, other: "Nutrients") -> "Nutrients":
        return Nutrients(**{
            item.name: getattr(self, item.name) + getattr(other, item.name)
            for item in fields(self)
        })

    def __truediv__(self, divisor: Decimal) -> "Nutrients":
        return Nutrients(**{
            item.name: getattr(self, item.name) / divisor
            for item in fields(self)
        })

    def for_amount(self, amount_g: Decimal) -> "Nutrients":
        return Nutrients(**{
            item.name: getattr(self, item.name) * amount_g / HUNDRED
            for item in fields(self)
        })

    def for_quantity(self, amount: Decimal, basis: str = BASIS_GRAMS) -> "Nutrients":
        """Nutrients for ``amount`` grams (per-100 g values) or ``amount`` items (per-item values)."""
        if basis == BASIS_COUNT:
            return self * amount
        return self.for_amount(amount)

    def per_100g_of_yield(self, yield_g: Decimal) -> "Nutrients":
        return self * HUNDRED / yield_g

    def __mul__(self, multiplier: Decimal) -> "Nutrients":
        return Nutrients(**{
            item.name: getattr(self, item.name) * multiplier
            for item in fields(self)
        })

    @classmethod
    def from_mapping(cls, values: Mapping[str, Decimal]) -> "Nutrients":
        return cls(**{item.name: values.get(item.name, ZERO) for item in fields(cls)})
