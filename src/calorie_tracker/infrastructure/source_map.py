from dataclasses import dataclass
from decimal import Decimal


CSV_HEADER_ROW = 4
FOOD_NAME_HEADER = "food_name"

NUTRIENT_HEADERS = {
    "calories": "calories / 100g",
    "fat": "fat / 100g",
    "saturated_fat": "saturated_fat / 100g",
    "carbohydrates": "carbohydrates / 100g",
    "sugars": "sugars / 100g",
    "protein": "protein / 100g",
    "fiber": "fiber / 100g",
    "omega_3": "omega-3 / 100g",
    "omega_6": "omega-6 / 100g",
}


@dataclass(frozen=True)
class RecipeSeed:
    name: str
    yield_g: Decimal
    ingredients: tuple[tuple[str, Decimal], ...]


COCOA_ICE_CREAM = RecipeSeed(
    name="Cocoa Ice Cream",
    yield_g=Decimal("652"),
    ingredients=(
        ("Coconut milk", Decimal("300")),
        ("Verea yellow low fat milk", Decimal("300")),
        ("Cocoa powder", Decimal("15")),
        ("Cacao protein", Decimal("30")),
        ("PB2 powder", Decimal("7")),
    ),
)
