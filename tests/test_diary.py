import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food
from calorie_tracker.infrastructure.database import Database
from calorie_tracker.infrastructure.repositories import DiaryRepository, FoodRepository, RecipeRepository
from calorie_tracker.application.diary import DiaryService, MEALS


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


if __name__ == "__main__":
    unittest.main()
