import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient, preview_recipe
from calorie_tracker.infrastructure.database import Database
from calorie_tracker.infrastructure.repositories import DiaryRepository, FoodRepository, RecipeRepository
from calorie_tracker.application.diary import DiaryEntryInput, DiaryService, MEALS


class DiaryServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "tracker.sqlite3"
        self.database = Database(self.database_path)
        self.database.initialize()
        self.foods = FoodRepository(self.database)
        self.recipes = RecipeRepository(self.database, self.foods)
        self.diary_repository = DiaryRepository(self.database)
        self.service = DiaryService(self.foods, self.recipes, self.diary_repository)
        self.food = Food("food-1", "Skyr", Nutrients(
            calories=Decimal("210"), protein=Decimal("12"), carbohydrates=Decimal("24"), fat=Decimal("8"),
        ))
        self.foods.save(self.food)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_autosaves_entry_and_day_totals_by_meal(self):
        entry = self.service.add_item("2026-09-30", "Breakfast", "food-1", Decimal("50"))

        self.assertEqual(entry.nutrients.calories, Decimal("105"))
        self.assertEqual(self.diary_repository.entries_on("2026-09-30"), (entry,))
        totals = self.service.totals_for_day("2026-09-30")
        self.assertEqual(totals.total.calories, Decimal("105"))
        self.assertEqual(totals.meals["Breakfast"].protein, Decimal("6"))
        self.assertEqual(totals.meals["Lunch"], Nutrients())

    def test_day_total_sums_all_nutrients_from_saved_snapshots(self):
        food_a = Food("food-a", "Food A", Nutrients(
            calories=Decimal("123.4567"), fat=Decimal("8.1234"), saturated_fat=Decimal("2.3456"),
            carbohydrates=Decimal("24.5678"), sugars=Decimal("9.8765"), protein=Decimal("12.3456"),
            fiber=Decimal("3.4567"), omega_3=Decimal("1.2345"), omega_6=Decimal("0.9876"),
        ))
        food_b = Food("food-b", "Food B", Nutrients(
            calories=Decimal("210.1234"), fat=Decimal("3.2109"), saturated_fat=Decimal("1.1098"),
            carbohydrates=Decimal("11.2223"), sugars=Decimal("4.3334"), protein=Decimal("17.4445"),
            fiber=Decimal("5.5556"), omega_3=Decimal("0.6667"), omega_6=Decimal("1.7778"),
        ))
        self.foods.save(food_a)
        self.foods.save(food_b)

        first = self.service.add_item("2026-09-30", "Breakfast", "food-a", Decimal("100"))
        second = self.service.add_item("2026-09-30", "Dinner", "food-b", Decimal("50"))
        totals = self.service.totals_for_day("2026-09-30")

        expected = first.nutrients + second.nutrients
        self.assertEqual(totals.total, expected)
        self.assertEqual(totals.meals["Breakfast"], first.nutrients)
        self.assertEqual(totals.meals["Dinner"], second.nutrients)
        self.assertEqual(totals.meals["Lunch"], Nutrients())
        self.assertEqual(totals.meals["Snacks"], Nutrients())

    def test_day_total_ignores_entries_from_other_dates(self):
        self.service.add_item("2026-09-29", "Breakfast", "food-1", Decimal("100"))
        entry = self.service.add_item("2026-09-30", "Breakfast", "food-1", Decimal("50"))

        totals = self.service.totals_for_day("2026-09-30")

        self.assertEqual(totals.total, entry.nutrients)

    def test_recipe_entry_and_food_entry_are_both_included_in_day_total(self):
        self.foods.save(Food("recipe-food", "Recipe Food", Nutrients(
            calories=Decimal("100"), protein=Decimal("10"), carbohydrates=Decimal("20"), fat=Decimal("5"),
        )))
        recipe = RecipeDraft(
            "Recipe", Decimal("200"),
            (RecipeIngredient(self.foods.get("recipe-food"), Decimal("100")),),
        )
        self.recipes.save("recipe-1", recipe, preview_recipe(recipe))
        food_entry = self.service.add_item("2026-09-30", "Breakfast", "food-1", Decimal("50"))
        recipe_entry = self.service.add_item("2026-09-30", "Lunch", "recipe-1", Decimal("100"))

        totals = self.service.totals_for_day("2026-09-30")
        self.assertEqual(totals.total, food_entry.nutrients + recipe_entry.nutrients)
        self.assertEqual(totals.total.calories, Decimal("155"))
        self.assertEqual(totals.total.protein, Decimal("11"))

    def test_edit_amount_uses_saved_nutrition_snapshot_after_catalogue_change(self):
        entry = self.service.add_item("2026-09-30", "Lunch", "food-1", Decimal("50"))
        self.foods.save(Food("food-1", "Skyr revised", Nutrients(calories=Decimal("900"), protein=Decimal("60"))))

        updated = self.service.edit_amount(entry.id, Decimal("100"))

        self.assertEqual(updated.display_name, "Skyr")
        self.assertEqual(updated.nutrients_per_100g.calories, Decimal("210"))
        self.assertEqual(updated.nutrients.calories, Decimal("210"))

    def test_repeat_creates_a_separate_saved_entry_with_the_same_snapshot(self):
        entry = self.service.add_item("2026-09-30", "Dinner", "food-1", Decimal("125"))

        repeated = self.service.repeat_entry(entry.id)

        self.assertNotEqual(repeated.id, entry.id)
        self.assertEqual(repeated.amount_g, entry.amount_g)
        self.assertEqual(repeated.nutrients, entry.nutrients)
        self.assertEqual(len(self.diary_repository.entries_on("2026-09-30")), 2)

    def test_delete_returns_entry_for_undo_and_restore_keeps_its_snapshot(self):
        entry = self.service.add_item("2026-09-30", "Snacks", "food-1", Decimal("80"))

        deleted = self.service.delete_entry(entry.id)
        self.assertEqual(self.diary_repository.entries_on("2026-09-30"), ())
        restored = self.service.restore_entry(deleted)

        self.assertEqual(restored, entry)
        self.assertEqual(self.diary_repository.entries_on("2026-09-30"), (entry,))

    def test_invalid_date_meal_and_amount_are_rejected_without_saving(self):
        invalid_inputs = [
            ("30/09/2026", "Lunch", Decimal("50")),
            ("2026-09-30", "Brunch", Decimal("50")),
            ("2026-09-30", "Lunch", Decimal("0")),
            ("2026-09-30", "Lunch", Decimal("-1")),
        ]
        for diary_date, meal, amount in invalid_inputs:
            with self.subTest(date=diary_date, meal=meal, amount=amount):
                with self.assertRaises(ValueError):
                    self.service.add_item(diary_date, meal, "food-1", amount)
        self.assertEqual(self.diary_repository.entries_on("2026-09-30"), ())
        self.assertEqual(MEALS, ("Breakfast", "Lunch", "Dinner", "Snacks"))

    def test_entry_remains_after_service_and_database_are_reopened(self):
        entry = self.service.add_item("2026-10-01", "Breakfast", "food-1", Decimal("40"))
        reopened = DiaryRepository(Database(self.database_path))

        self.assertEqual(reopened.entries_on("2026-10-01"), (entry,))

    def test_batch_add_imports_entries_to_selected_day_and_meals_with_snapshots(self):
        entries = self.service.add_items_batch("2026-09-30", (
            DiaryEntryInput("Breakfast", "food-1", Decimal("50")),
            DiaryEntryInput("Snacks", "food-1", Decimal("25")),
        ))

        self.assertEqual(tuple(entry.meal for entry in entries), ("Breakfast", "Snacks"))
        self.assertEqual(tuple(entry.diary_date for entry in entries), ("2026-09-30", "2026-09-30"))
        self.assertEqual(self.diary_repository.entries_on("2026-09-30"), entries)
        self.assertEqual(tuple(entry.nutrients.calories for entry in entries), (Decimal("105"), Decimal("52.5")))

    def test_batch_add_validates_every_row_before_writing_any_entries(self):
        with self.assertRaises(ValueError):
            self.service.add_items_batch("2026-09-30", (
                DiaryEntryInput("Breakfast", "food-1", Decimal("50")),
                DiaryEntryInput("Brunch", "food-1", Decimal("25")),
            ))

        self.assertEqual(self.diary_repository.entries_on("2026-09-30"), ())


if __name__ == "__main__":
    unittest.main()
