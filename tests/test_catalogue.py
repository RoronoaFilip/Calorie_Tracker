import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient
from calorie_tracker.infrastructure.database import Database
from calorie_tracker.infrastructure.repositories import FoodRepository, RecipeRepository
from calorie_tracker.application.catalogue import CatalogueService, RecipeValidationError


class CatalogueServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "tracker.sqlite3")
        self.database.initialize()
        self.foods = FoodRepository(self.database)
        self.recipes = RecipeRepository(self.database, self.foods)
        self.service = CatalogueService(self.foods, self.recipes)
        self.food = Food("oats", "Oats", Nutrients(calories=Decimal("380"), protein=Decimal("13")))
        self.foods.save(self.food)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_recipe_round_trips_with_calculated_nutrition_and_ingredients(self):
        draft = RecipeDraft("Oat bowl", Decimal("150"), (RecipeIngredient(self.food, Decimal("100")),))

        preview = self.service.save_recipe("recipe-1", draft)
        saved = self.recipes.get("recipe-1")

        self.assertEqual(preview.per_100g.calories, Decimal("253.3333333333333333333333333"))
        self.assertEqual(saved.draft, draft)
        self.assertEqual(saved.per_100g.calories, preview.per_100g.calories)
        self.assertTrue(saved.active)

    def test_duplicate_recipe_name_and_yield_difference_are_nonblocking_warnings(self):
        first = RecipeDraft("Oat bowl", Decimal("100"), (RecipeIngredient(self.food, Decimal("100")),))
        self.service.save_recipe("recipe-1", first)
        duplicate = RecipeDraft("Oat bowl", Decimal("150"), (RecipeIngredient(self.food, Decimal("100")),))

        preview = self.service.validate_recipe(duplicate)

        self.assertEqual(preview.errors, ())
        self.assertEqual({item.field for item in preview.warnings}, {"name", "yield_g"})
        self.service.save_recipe("recipe-2", duplicate)
        self.assertIsNotNone(self.recipes.get("recipe-2"))

    def test_failed_edit_does_not_replace_saved_recipe_ingredients(self):
        original = RecipeDraft("Oat bowl", Decimal("100"), (RecipeIngredient(self.food, Decimal("100")),))
        self.service.save_recipe("recipe-1", original)
        invalid = RecipeDraft("Oat bowl", Decimal("0"), ())

        with self.assertRaises(RecipeValidationError):
            self.service.save_recipe("recipe-1", invalid)

        self.assertEqual(self.recipes.get("recipe-1").draft, original)

    def test_archive_keeps_food_record_but_removes_it_from_default_search(self):
        self.foods.archive("oats")

        self.assertEqual(self.foods.search("oats"), ())
        self.assertFalse(self.foods.search("oats", include_archived=True)[0].active)


if __name__ == "__main__":
    unittest.main()
