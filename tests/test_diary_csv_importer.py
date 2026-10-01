import csv
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food
from calorie_tracker.infrastructure.database import Database
from calorie_tracker.infrastructure.diary_csv_importer import (
    CsvDiaryImporter,
    DiaryCsvFormatError,
)
from calorie_tracker.infrastructure.repositories import FoodRepository


class DiaryCsvImporterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        database = Database(Path(self.temp_dir.name) / "tracker.sqlite3")
        database.initialize()
        self.foods = FoodRepository(database)
        self.foods.save(Food("oats", "Oats", Nutrients(calories=Decimal("380"))))
        self.foods.save(Food("banana", "Banana", Nutrients(calories=Decimal("90"))))
        self.importer = CsvDiaryImporter(self.foods)

    def _write_csv(self, rows, preamble=False):
        path = Path(self.temp_dir.name) / "diary.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            if preamble:
                writer.writerows([["Daily summary"], ["Instructions"], [""], [""]])
            writer.writerows(rows)
        return path

    def test_preview_matches_foods_and_reads_optional_meal_column(self):
        path = self._write_csv([
            ["food_name", "grams_eaten (all meals)", "meal", "calories / 100g"],
            ["Oats", "45.5", "Breakfast", "380"],
            ["banana", "120", "snack", "90"],
        ], preamble=True)

        preview = self.importer.preview(path)

        self.assertEqual(len(preview.rows), 2)
        self.assertEqual(preview.rows[0].catalogue_item_id, "oats")
        self.assertEqual(preview.rows[0].amount_g, Decimal("45.5"))
        self.assertEqual(preview.rows[0].meal, "Breakfast")
        self.assertEqual(preview.rows[1].meal, "Snacks")
        self.assertEqual(preview.importable_count, 2)
        self.assertEqual(preview.rows[0].source_row, 6)

    def test_preview_accepts_header_first_csv_and_flags_rows_requiring_meals(self):
        path = self._write_csv([
            ["food_name", "grams_eaten (all meals)"],
            ["Oats", "50"],
        ])

        preview = self.importer.preview(path)

        self.assertIsNone(preview.rows[0].meal)
        self.assertEqual(preview.needs_meal_assignment, (preview.rows[0],))

    def test_preview_keeps_invalid_rows_visible_without_matching_partial_food_names(self):
        path = self._write_csv([
            ["food_name", "grams_eaten (all meals)", "meal"],
            ["Oat", "50", "Lunch"],
            ["Banana", "not-a-number", "Dinner"],
            ["Oats", "0", "Dinner"],
        ])

        preview = self.importer.preview(path)

        self.assertEqual(preview.importable_count, 0)
        self.assertEqual(len(preview.skipped_rows), 3)
        self.assertIn("not found", preview.rows[0].error.casefold())
        self.assertIn("number", preview.rows[1].error.casefold())
        self.assertIn("greater than 0", preview.rows[2].error)

    def test_preview_reports_every_validation_problem_found_on_a_row(self):
        path = self._write_csv([
            ["food_name", "grams_eaten (all meals)", "meal"],
            ["Unknown food", "not-a-number", "Brunch"],
        ])

        row = self.importer.preview(path).rows[0]

        self.assertIn("number", row.error.casefold())
        self.assertIn("not found", row.error.casefold())
        self.assertIn("meal", row.error.casefold())

    def test_preview_rejects_duplicate_required_headers_with_format_guidance(self):
        path = self._write_csv([
            ["food_name", "food_name", "grams_eaten (all meals)"],
            ["Oats", "Banana", "50"],
        ])

        with self.assertRaises(DiaryCsvFormatError) as context:
            self.importer.preview(path)

        self.assertIn("duplicate", str(context.exception).casefold())
        self.assertIn("Expected header", str(context.exception))

    def test_preview_does_not_guess_between_duplicate_catalogue_names(self):
        self.foods.save(Food("oats-duplicate", " oats ", Nutrients(calories=Decimal("999"))))
        path = self._write_csv([
            ["food_name", "grams_eaten (all meals)"],
            ["Oats", "50"],
        ])

        row = self.importer.preview(path).rows[0]

        self.assertIsNone(row.catalogue_item_id)
        self.assertIn("multiple active catalogue matches", row.error)

    def test_preview_rejects_csv_without_required_food_or_amount_header(self):
        path = self._write_csv([["name", "amount"], ["Oats", "50"]])

        with self.assertRaises(DiaryCsvFormatError) as context:
            self.importer.preview(path)
        self.assertIn("Expected header: food_name,grams_eaten (all meals),meal", str(context.exception))
        self.assertIn("Oats,45.5,Breakfast", str(context.exception))

    def test_preview_reports_malformed_csv_syntax_with_expected_format(self):
        path = Path(self.temp_dir.name) / "broken.csv"
        path.write_text(
            'food_name,grams_eaten (all meals),meal\n"Oats,50,Breakfast\n',
            encoding="utf-8",
        )

        with self.assertRaises(DiaryCsvFormatError) as context:
            self.importer.preview(path)

        self.assertIn("Expected header", str(context.exception))
        self.assertIn("Example row", str(context.exception))


if __name__ == "__main__":
    unittest.main()
