from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Mapping


ZERO = Decimal("0")
HUNDRED = Decimal("100")


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
