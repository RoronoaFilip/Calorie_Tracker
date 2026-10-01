from dataclasses import replace
import re

from calorie_tracker.domain.recipes import RecipeDraft, RecipePreview, ValidationMessage, preview_recipe
from calorie_tracker.infrastructure.repositories import FoodRepository, RecipeRepository


class RecipeValidationError(ValueError):
    def __init__(self, preview: RecipePreview):
        super().__init__("Recipe validation failed.")
        self.preview = preview


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
