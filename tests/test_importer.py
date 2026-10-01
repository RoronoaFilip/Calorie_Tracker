import csv
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food
from calorie_tracker.infrastructure.database import Database
from calorie_tracker.infrastructure.importer import CsvFoodImporter, ImportFormatError
from calorie_tracker.infrastructure.repositories import FoodRepository


HEADER = [
    "food_name", "grams_eaten (all meals)", "calories / 100g", "fat / 100g",
    "saturated_fat / 100g", "carbohydrates / 100g", "sugars / 100g",
    "protein / 100g", "fiber / 100g", "omega-3 / 100g", "omega-6 / 100g",
    "calories total",
]


def write_csv(directory: str, records: list[list[str]]) -> Path:
    path = Path(directory) / "foods.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerows([["report title"], ["instruction row"], ["daily total"], [""], HEADER, *records])
    return path


def row(name: str, calories: str = "100") -> list[str]:
    return [name, "250", calories, "1", "0.2", "10", "2", "5", "3", "0.4", "0.1", "250"]


class CsvFoodImporterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "data" / "tracker.sqlite3")
        self.database.initialize()
        self.foods = FoodRepository(self.database)
        self.importer = CsvFoodImporter(self.foods)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_preview_reads_only_mapped_per_100g_columns_and_does_not_write(self):
        path = write_csv(self.temp_dir.name, [row("Café, plain")])

        preview = self.importer.preview(path)

        self.assertEqual(preview.report.rows_read, 1)
        self.assertEqual(preview.report.importable, 1)
        self.assertEqual(preview.foods[0].food.name, "Café, plain")
        self.assertEqual(str(preview.foods[0].food.nutrients_per_100g.calories), "100")
        self.assertEqual(preview.report.ignored_headers, ("grams_eaten (all meals)", "calories total"))
        self.assertIsNone(self.foods.get(preview.foods[0].food.id))

    def test_preview_reports_blank_names_duplicates_and_malformed_values(self):
        malformed = row("Broken", "not-a-number")
        path = write_csv(self.temp_dir.name, [row("Apple"), row(" apple "), ["", *row("x")[1:]], malformed])

        preview = self.importer.preview(path)

        self.assertEqual(preview.report.rows_read, 4)
        self.assertEqual(preview.report.importable, 1)
        self.assertEqual(preview.report.duplicate_names, 1)
        self.assertEqual(preview.report.blank_names, 1)
        self.assertEqual(preview.report.malformed_rows, 1)
        self.assertEqual(len(preview.report.row_errors), 1)
        self.assertIn("calories / 100g", preview.report.row_errors[0])

    def test_preview_rejects_missing_exact_source_header(self):
        path = write_csv(self.temp_dir.name, [row("Apple")])
        text = path.read_text(encoding="utf-8").replace("protein / 100g", "protein per serving")
        path.write_text(text, encoding="utf-8")

        with self.assertRaisesRegex(ImportFormatError, "protein / 100g"):
            self.importer.preview(path)

    def test_ice_cream_rows_are_excluded_from_basic_food_import(self):
        path = write_csv(self.temp_dir.name, [row("Cocoa Ice Cream"), row("Vanilla ice cream")])

        preview = self.importer.preview(path)

        self.assertEqual(preview.report.importable, 0)
        self.assertEqual(preview.report.excluded_ice_cream_rows, 2)
        self.assertEqual(self.importer.apply(preview).imported, 0)

    def test_verified_project_source_previews_26_basic_foods_and_excludes_both_ice_creams(self):
        source = Path(__file__).resolve().parents[1] / "macros_base - All Foods.csv"

        preview = self.importer.preview(source)

        self.assertEqual(preview.report.rows_read, 28)
        self.assertEqual(preview.report.importable, 26)
        self.assertEqual(preview.report.excluded_ice_cream_rows, 2)
        chia = next(item.food for item in preview.foods if item.food.name == "Chia seeds")
        self.assertEqual(chia.nutrients_per_100g.calories, Decimal("452.00"))

    def test_apply_is_idempotent_and_never_overwrites_a_user_food(self):
        path = write_csv(self.temp_dir.name, [row("Apple")])
        preview = self.importer.preview(path)
        first = self.importer.apply(preview)
        second = self.importer.apply(preview)

        self.assertEqual(first.imported, 1)
        self.assertEqual(second.already_present, 1)
        self.assertEqual(len(self.foods.search("apple")), 1)

        banana_preview = self.importer.preview(write_csv(self.temp_dir.name, [row("Banana")]))
        self.foods.save(Food("manual", "Banana", Nutrients(calories=Decimal("222"))))
        blocked = self.importer.apply(banana_preview)

        self.assertEqual(blocked.name_conflicts, 1)
        self.assertEqual(self.foods.get("manual").nutrients_per_100g.calories, Decimal("222"))


if __name__ == "__main__":
    unittest.main()
