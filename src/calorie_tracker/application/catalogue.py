from dataclasses import dataclass, replace
import uuid

from calorie_tracker.domain.nutrition import BASIS_COUNT
from calorie_tracker.domain.recipes import (
    RecipeDraft,
    RecipeIngredient,
    RecipePreview,
    ValidationMessage,
    preview_recipe,
)
from calorie_tracker.infrastructure.repositories import FoodRepository, RecipeRepository


class RecipeValidationError(ValueError):
    def __init__(self, preview: RecipePreview):
        super().__init__("Recipe validation failed.")
        self.preview = preview


@dataclass(frozen=True)
class RecipeImportResult:
    imported: int
    failed: tuple[tuple[str, str], ...]  # (recipe name, reason)


@dataclass(frozen=True)
class RestorePlan:
    """An archived recipe rebuilt from today's foods, and why it should be reviewed before it is restored."""

    recipe_id: str
    draft: RecipeDraft
    problems: tuple[str, ...]  # empty when the recipe can be restored exactly as it was

    @property
    def needs_review(self) -> bool:
        return bool(self.problems)


def _basis_phrase(basis: str) -> str:
    return "per item" if basis == BASIS_COUNT else "per 100 g"


class CatalogueService:
    def __init__(self, foods: FoodRepository, recipes: RecipeRepository):
        self.foods = foods
        self.recipes = recipes

    def validate_recipe(self, draft: RecipeDraft, editing_id: str | None = None) -> RecipePreview:
        preview = preview_recipe(draft)
        warnings = list(preview.warnings)
        if not preview.errors and self.recipes.name_exists(draft.name, editing_id):
            warnings.append(ValidationMessage(
                "name", "A recipe with this name already exists. Saving will keep both catalogue entries."
            ))
        return replace(preview, warnings=tuple(warnings))

    def save_recipe(self, recipe_id: str, draft: RecipeDraft) -> RecipePreview:
        preview = self.validate_recipe(draft, editing_id=recipe_id)
        if preview.errors:
            raise RecipeValidationError(preview)
        self.recipes.save(recipe_id, draft, preview)
        return preview

    def import_recipes(self, drafts: tuple[RecipeDraft, ...]) -> RecipeImportResult:
        """Save new recipes one by one; a recipe that fails is reported and does not stop the others."""
        imported = 0
        failed: list[tuple[str, str]] = []
        for draft in drafts:
            try:
                self.save_recipe(str(uuid.uuid4()), draft)
                imported += 1
            except (RecipeValidationError, ValueError) as error:
                reason = " ".join(item.message for item in error.preview.errors) \
                    if isinstance(error, RecipeValidationError) else str(error)
                failed.append((draft.name, reason))
        return RecipeImportResult(imported, tuple(failed))

    # ---- archive -----------------------------------------------------------------------------------

    def prepare_restore(self, recipe_id: str) -> RestorePlan | None:
        """Rebuild an archived recipe from the foods as they are now and list what changed since it was archived.

        Foods can be edited while a recipe is archived (e.g. changed from per 100 g to per item); an ingredient
        amount in grams then no longer means what it did, so the person must check the recipe before it returns.
        """
        archived = self.recipes.get_archived(recipe_id)
        if archived is None:
            return None
        ingredients: list[RecipeIngredient] = []
        problems: list[str] = []
        for item in archived.ingredients:
            food = self.foods.get(item.food_id)
            if food is None:
                problems.append(f"“{item.food_name}” no longer exists, so it was left out. Add an ingredient to replace it.")
                continue
            if not food.active:
                problems.append(f"“{food.name}” is archived. Restore it first, or replace it with another food.")
            if food.basis != item.basis:
                problems.append(
                    f"“{food.name}” was {_basis_phrase(item.basis)} when this recipe was archived but is now "
                    f"{_basis_phrase(food.basis)}, so the amount ({item.amount_g.normalize():f}) needs to be checked."
                )
            ingredients.append(RecipeIngredient(food, item.amount_g))
        draft = RecipeDraft(archived.name, archived.yield_g, tuple(ingredients))
        if not problems and preview_recipe(draft).errors:
            problems.append("The recipe is no longer valid with today's foods. Please review it.")
        return RestorePlan(recipe_id, draft, tuple(problems))

    def restore_recipe(self, recipe_id: str, draft: RecipeDraft) -> RecipePreview:
        """Put an archived recipe back (with the checked ``draft``) and take it out of the archive."""
        preview = self.validate_recipe(draft, editing_id=recipe_id)
        if preview.errors:
            raise RecipeValidationError(preview)
        self.recipes.restore(recipe_id, draft, preview)
        return preview
