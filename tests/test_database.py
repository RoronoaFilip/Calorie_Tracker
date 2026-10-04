import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food
from calorie_tracker.infrastructure.database import Database
from calorie_tracker.infrastructure.repositories import FoodRepository, SettingsRepository


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "data" / "tracker.sqlite3"
        self.database = Database(self.database_path)
        self.database.initialize()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initialize_creates_parent_database_and_versioned_schema(self):
        self.assertTrue(self.database_path.is_file())
        with self.database.read_connection() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 3)
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        self.assertIn("catalogue_items", tables)
        self.assertIn("diary_entries", tables)
        self.assertIn("preferences", tables)

    def test_food_repository_round_trips_exact_decimal_values_and_searches(self):
        repository = FoodRepository(self.database)
        food = Food("food-1", "Pink Skyr", Nutrients(
            calories=Decimal("52"), protein=Decimal("8.500"),
        ))
        repository.save(food, source_key="csv:Pink Skyr")

        self.assertEqual(repository.get("food-1"), food)
        self.assertEqual([item.id for item in repository.search("skyr")], ["food-1"])
        self.assertEqual(repository.search("missing"), ())

    def test_settings_repository_round_trips_optional_targets(self):
        repository = SettingsRepository(self.database)
        target = {"calories": "2100", "protein": "130.5", "carbohydrates": None, "fat": "70"}

        repository.set_json("daily_targets", target)

        self.assertEqual(repository.get_json("daily_targets"), target)
        self.assertIsNone(repository.get_json("preferred_unit"))

    def test_database_transaction_rolls_back_all_writes_after_failure(self):
        with self.assertRaises(RuntimeError):
            with self.database.transaction() as connection:
                connection.execute(
                    "INSERT INTO preferences(key, value_json) VALUES (?, ?)",
                    ("temporary", '"value"'),
                )
                raise RuntimeError("abort this transaction")

        self.assertIsNone(SettingsRepository(self.database).get_json("temporary"))

    def test_unknown_schema_version_is_rejected(self):
        with self.database.transaction() as connection:
            connection.execute("PRAGMA user_version = 99")

        with self.assertRaisesRegex(RuntimeError, "newer than this application"):
            self.database.initialize()


if __name__ == "__main__":
    unittest.main()
