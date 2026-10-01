from dataclasses import dataclass
from decimal import Decimal

from .nutrition import Nutrients, ZERO


@dataclass(frozen=True)
class Food:
    id: str
    name: str
    nutrients_per_100g: Nutrients
    active: bool = True


@dataclass(frozen=True)
class RecipeIngredient:
    food: Food
    amount_g: Decimal


@dataclass(frozen=True)
class RecipeDraft:
    name: str
    yield_g: Decimal
    ingredients: tuple[RecipeIngredient, ...]


@dataclass(frozen=True)
class ValidationMessage:
    field: str
    message: str


@dataclass(frozen=True)
class RecipePreview:
    total_nutrients: Nutrients
    per_100g: Nutrients
    ingredient_weight_g: Decimal
    errors: tuple[ValidationMessage, ...]
    warnings: tuple[ValidationMessage, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def preview_recipe(draft: RecipeDraft) -> RecipePreview:
    errors: list[ValidationMessage] = []
    warnings: list[ValidationMessage] = []
    if not draft.name.strip():
        errors.append(ValidationMessage("name", "Enter a recipe name."))
    if draft.yield_g <= ZERO:
        errors.append(ValidationMessage("yield_g", "Final yield must be greater than 0 g."))
    if not draft.ingredients:
        errors.append(ValidationMessage("ingredients", "Add at least one ingredient."))

    ingredient_weight = ZERO
    total = Nutrients()
    for index, ingredient in enumerate(draft.ingredients):
        field = f"ingredients.{index}.amount_g"
        if ingredient.amount_g <= ZERO:
            errors.append(ValidationMessage(field, "Ingredient amount must be greater than 0 g."))
            continue
        if not ingredient.food.active:
            errors.append(ValidationMessage(
                f"ingredients.{index}.food", f"{ingredient.food.name} is archived and cannot be used."
            ))
            continue
        ingredient_weight += ingredient.amount_g
        total += ingredient.food.nutrients_per_100g.for_amount(ingredient.amount_g)

    if draft.yield_g > ZERO and ingredient_weight != draft.yield_g:
        warnings.append(ValidationMessage(
            "yield_g",
            f"Final yield ({draft.yield_g:g} g) differs from the combined ingredient weight "
            f"({ingredient_weight:g} g). Confirm this is the measured yield after preparation.",
        ))

    if errors:
        return RecipePreview(total, Nutrients(), ingredient_weight, tuple(errors), tuple(warnings))
    return RecipePreview(total, total.per_100g_of_yield(draft.yield_g), ingredient_weight, (), tuple(warnings))
