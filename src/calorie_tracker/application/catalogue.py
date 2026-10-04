from dataclasses import dataclass, replace
import uuid

from calorie_tracker.domain.recipes import RecipeDraft, RecipePreview, ValidationMessage, preview_recipe
from calorie_tracker.infrastructure.repositories import FoodRepository, RecipeRepository


class RecipeValidationError(ValueError):
    def __init__(self, preview: RecipePreview):
        super().__init__("Recipe validation failed.")
        self.preview = preview


@dataclass(frozen=True)
class RecipeImportResult:
    imported: int
    failed: tuple[tuple[str, str], ...]  # (recipe name, reason)


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
