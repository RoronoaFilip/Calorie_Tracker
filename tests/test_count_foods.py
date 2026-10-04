import logging
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from calorie_tracker.bootstrap import build_services
from calorie_tracker.domain.diary import MealPortion
from calorie_tracker.domain.nutrition import BASIS_COUNT, Nutrients
from calorie_tracker.domain.recipes import Food, RecipeDraft, RecipeIngredient, preview_recipe
from calorie_tracker.application.diary import DiaryEntryInput
from calorie_tracker.infrastructure.backup import BackupService
from calorie_tracker.infrastructure.database import Database
from calorie_tracker.infrastructure.repositories import BasisInUseError

_V1_SCHEMA = """
CREATE TABLE catalogue_items (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, normalized_name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('food', 'recipe')), archived INTEGER NOT NULL DEFAULT 0,
    nutrients_json TEXT NOT NULL, recipe_yield_g TEXT, source_key TEXT UNIQUE, source_row INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE recipe_ingredients (
    recipe_id TEXT NOT NULL REFERENCES catalogue_items(id) ON DELETE CASCADE, position INTEGER NOT NULL,
    food_id TEXT NOT NULL REFERENCES catalogue_items(id) ON DELETE RESTRICT, amount_g TEXT NOT NULL,
    PRIMARY KEY (recipe_id, position));
CREATE TABLE diary_entries (
    id TEXT PRIMARY KEY, diary_date TEXT NOT NULL, meal TEXT NOT NULL,
    catalogue_item_id TEXT REFERENCES catalogue_items(id) ON DELETE SET NULL, display_name TEXT NOT NULL,
    amount_g TEXT NOT NULL, nutrients_snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE preferences (key TEXT PRIMARY KEY, value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE recent_foods (catalogue_item_id TEXT PRIMARY KEY REFERENCES catalogue_items(id) ON DELETE CASCADE,
    last_used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
INSERT INTO catalogue_items (id, name, normalized_name, kind, nutrients_json)
    VALUES ('oats', 'Oats', 'oats', 'food', '{"calories": "380"}');
INSERT INTO diary_entries (id, diary_date, meal, catalogue_item_id, display_name, amount_g, nutrients_snapshot_json)
    VALUES ('e1', '2026-01-02', 'Breakfast', 'oats', 'Oats', '50', '{"calories": "380"}');
PRAGMA user_version = 1;
"""


def egg() -> Food:
    return Food("egg", "Egg", Nutrients(calories=Decimal("70"), protein=Decimal("6")), True, BASIS_COUNT)


class CountedFoodTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.services = build_services(self.root / "data" / "tracker.sqlite3")
        self.addCleanup(self._close_log_handlers)
        self.services.foods.save(egg())
        self.services.foods.save(Food("oats", "Oats", Nutrients(calories=Decimal("380"))))

    def _close_log_handlers(self):
        logger = logging.getLogger("calorie_tracker")
        for handler in tuple(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def test_basis_is_saved_and_defaults_to_grams(self):
        self.assertEqual(self.services.foods.get("egg").basis, "count")
        self.assertEqual(self.services.foods.get("oats").basis, "g")

    def test_basis_can_be_changed_when_no_recipe_uses_the_food(self):
        self.services.foods.save(Food("egg", "Egg", egg().nutrients_per_100g, True, "g"))
        self.assertEqual(self.services.foods.get("egg").basis, "g")
        self.services.foods.save(egg())
        self.assertEqual(self.services.foods.get("egg").basis, "count")

    def test_basis_cannot_change_while_a_recipe_uses_the_food_and_diary_keeps_its_snapshot(self):
        entry = self.services.diary.add_item("2026-03-01", "Breakfast", "egg", Decimal("2"))
        self.services.catalogue.save_recipe("r1", RecipeDraft("Eggs", Decimal("100"), (
            RecipeIngredient(self.services.foods.get("egg"), Decimal("2")),
        )))
        with self.assertRaises(BasisInUseError) as caught:
            self.services.foods.save(Food("egg", "Egg", egg().nutrients_per_100g, True, "g"))
        self.assertIn("Eggs", str(caught.exception))
        self.assertEqual(self.services.foods.get("egg").basis, "count")
        self.assertEqual(self.services.foods.recipes_using("egg"), ("Eggs",))
        # editing other details of the same basis is still fine
        self.services.foods.save(Food("egg", "Egg L", egg().nutrients_per_100g, True, "count"))
        self.assertEqual(self.services.diary.diary.get(entry.id).basis, "count")

    def test_diary_history_keeps_its_basis_after_the_food_changes(self):
        entry = self.services.diary.add_item("2026-03-01", "Breakfast", "egg", Decimal("2"))
        self.services.foods.save(Food("egg", "Egg", egg().nutrients_per_100g, True, "g"))
        kept = self.services.diary.diary.get(entry.id)
        self.assertEqual((kept.basis, kept.nutrients.calories), ("count", Decimal("140")))

    def test_unknown_basis_is_rejected(self):
        with self.assertRaises(ValueError):
            self.services.foods.save(Food("x", "X", Nutrients(), True, "litre"))

    def test_counted_amount_multiplies_the_values_per_item(self):
        entry = self.services.diary.add_item("2026-03-01", "Breakfast", "egg", Decimal("2"))
        self.assertEqual(entry.basis, "count")
        self.assertEqual(entry.nutrients.calories, Decimal("140"))
        half = self.services.diary.add_item("2026-03-01", "Lunch", "egg", Decimal("0.5"))
        self.assertEqual(half.nutrients.protein, Decimal("3.0"))
        stored = self.services.diary.entries_for_day("2026-03-01")
        self.assertEqual([item.basis for item in stored], ["count", "count"])

    def test_weighed_foods_still_scale_per_100_g(self):
        entry = self.services.diary.add_item("2026-03-01", "Lunch", "oats", Decimal("50"))
        self.assertEqual(entry.basis, "g")
        self.assertEqual(entry.nutrients.calories, Decimal("190"))

    def test_batch_uses_each_foods_basis(self):
        entries = self.services.diary.add_items_batch("2026-03-01", (
            DiaryEntryInput("Breakfast", "egg", Decimal("3")), DiaryEntryInput("Lunch", "oats", Decimal("100")),
        ))
        self.assertEqual([entry.basis for entry in entries], ["count", "g"])
        self.assertEqual(entries[0].nutrients.calories, Decimal("210"))

    def test_editing_and_splitting_keep_the_count_basis(self):
        entry = self.services.diary.add_item("2026-03-01", "Breakfast", "egg", Decimal("3"))
        edited = self.services.diary.edit_amount(entry.id, Decimal("1.5"))
        self.assertEqual(self.services.diary.diary.get(entry.id).amount_g, Decimal("1.5"))
        parts = self.services.diary.split_entry(
            entry.id, (MealPortion("Lunch", Decimal("1")), MealPortion("Dinner", Decimal("0.5")))
        )
        self.assertEqual([part.basis for part in parts], ["count", "count"])
        self.assertEqual(edited.basis, "count")
        with self.assertRaisesRegex(ValueError, "pcs"):
            self.services.diary.edit_amount(parts[0].id, Decimal("0"))

    def test_recipe_with_counted_ingredient_uses_the_given_yield(self):
        oats = self.services.foods.get("oats")
        draft = RecipeDraft("Egg oats", Decimal("200"), (
            RecipeIngredient(oats, Decimal("100")), RecipeIngredient(self.services.foods.get("egg"), Decimal("2")),
        ))
        preview = preview_recipe(draft)
        self.assertTrue(preview.is_valid)
        self.assertEqual(preview.total_nutrients.calories, Decimal("520"))
        self.assertEqual(preview.per_100g.calories, Decimal("260"))
        self.assertEqual(preview.warnings, ())  # a counted item has no weight, so no yield mismatch warning
        self.services.catalogue.save_recipe("r1", draft)
        saved = self.services.recipes.get("r1")
        self.assertEqual(saved.draft.ingredients[1].food.basis, "count")
        self.assertEqual(saved.draft.ingredients[1].amount_g, Decimal("2"))

    def test_counted_ingredient_amount_message_says_pcs(self):
        draft = RecipeDraft("Bad", Decimal("100"), (RecipeIngredient(egg(), Decimal("0")),))
        messages = " ".join(error.message for error in preview_recipe(draft).errors)
        self.assertIn("0 pcs", messages)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    @staticmethod
    def _close_log_handlers():
        logger = logging.getLogger("calorie_tracker")
        for handler in tuple(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def _make_v1(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.executescript(_V1_SCHEMA)
        connection.commit()
        connection.close()

    def test_version_1_database_is_migrated_without_losing_data(self):
        path = self.root / "old.sqlite3"
        self._make_v1(path)
        database = Database(path)
        database.initialize()
        with database.read_connection() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 3)
            self.assertEqual(connection.execute("SELECT basis FROM catalogue_items").fetchone()[0], "g")
            self.assertEqual(connection.execute("SELECT basis, amount_g FROM diary_entries").fetchone()[:], ("g", "50"))
        database.initialize()  # running it again is harmless

    def test_version_1_backup_can_be_restored(self):
        services = build_services(self.root / "data" / "live.sqlite3")
        self.addCleanup(self._close_log_handlers)
        old_backup = self.root / "backup-v1.sqlite3"
        self._make_v1(old_backup)
        backups = BackupService(services.database, self.root / "data" / "backups")
        backups.restore(old_backup)
        self.assertEqual(services.foods.get("oats").basis, "g")
        self.assertEqual(len(services.diary.all_entries()), 1)


if __name__ == "__main__":
    unittest.main()
