import tempfile
import unittest
from pathlib import Path

from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food
from calorie_tracker.infrastructure.csv_reading import CsvTable
from calorie_tracker.infrastructure.database import Database
from calorie_tracker.infrastructure.diary_csv_importer import CsvDiaryImporter, DiaryCsvFormatError
from calorie_tracker.infrastructure.importer import CsvFoodImporter, ImportFormatError
from calorie_tracker.infrastructure.repositories import FoodRepository


def table(*rows: list[str]) -> CsvTable:
    return CsvTable([list(row) for row in rows], ",", "utf-8")


FOOD_HEADER = ["food_name", "calories / 100g", "protein / 100g", "fat / 100g", "carbohydrates / 100g"]


class RepairTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        database = Database(Path(self.temp.name) / "data" / "tracker.sqlite3")
        database.initialize()
        self.foods = FoodRepository(database)
        self.foods.save(Food("oats", "Oats", Nutrients()))
        self.food_importer = CsvFoodImporter(self.foods)
        self.diary_importer = CsvDiaryImporter(self.foods)


class FoodCsvRepairTests(RepairTestCase):
    def test_clean_table_has_no_issues(self):
        self.assertEqual(self.food_importer.issues_for(table(FOOD_HEADER, ["Rice", "360", "7", "1", "80"])), ())

    def test_missing_mandatory_column_points_at_the_header_row(self):
        issues = self.food_importer.issues_for(table(["food_name", "calories"], ["Rice", "360"]))

        self.assertEqual({issue.row for issue in issues}, {0})
        self.assertTrue(all(issue.column is None for issue in issues))
        text = " ".join(issue.message for issue in issues)
        for label in ("protein / 100g", "fat / 100g", "carbohydrates / 100g"):
            self.assertIn(label, text)
        self.assertNotIn("calories / 100g", text)

    def test_format_error_carries_the_issues_and_the_rows_for_repair(self):
        broken = table(["name", "calories"], ["Rice", "360"])
        with self.assertRaises(ImportFormatError) as caught:
            self.food_importer.preview_table(broken)
        self.assertIs(caught.exception.table, broken)
        self.assertTrue(caught.exception.issues)
        self.assertIn("Could not find a food catalogue header", str(caught.exception))

    def test_editing_a_header_cell_in_memory_repairs_the_file(self):
        rows = [["food_name", "calories"], ["Rice", "360"]]
        self.assertTrue(self.food_importer.issues_for(table(*rows)))
        fixed = [["food_name", "calories", "protein", "fat", "carbs"], ["Rice", "360", "7", "1", "80"]]
        self.assertEqual(self.food_importer.issues_for(table(*fixed)), ())
        self.assertEqual(len(self.food_importer.preview_table(table(*fixed)).foods), 1)

    def test_bad_values_are_pinned_to_their_cells(self):
        issues = self.food_importer.issues_for(table(
            FOOD_HEADER, ["Rice", "360", "7", "1", "80"], ["Barley", "lots", "5", "", "20"], ["", "1", "1", "1", "1"],
        ))
        by_cell = {(issue.row, issue.column): issue.message for issue in issues}

        self.assertEqual(set(by_cell), {(2, 1), (2, 3), (3, 0)})
        self.assertIn("“lots”", by_cell[(2, 1)])
        self.assertIn("empty", by_cell[(2, 3)])
        self.assertIn("blank", by_cell[(3, 0)])

    def test_issues_follow_a_header_that_is_not_on_the_first_row(self):
        issues = self.food_importer.issues_for(table(
            ["Report"], [""], FOOD_HEADER, ["Rice", "oops", "7", "1", "80"],
        ))
        self.assertEqual([(issue.row, issue.column) for issue in issues], [(3, 1)])

    def test_short_rows_and_empty_files_do_not_crash(self):
        self.assertTrue(self.food_importer.issues_for(table(FOOD_HEADER, ["Rice"])))
        self.assertEqual(self.food_importer.issues_for(table())[0].message, "The file is empty.")

    def test_preview_from_a_path_still_works(self):
        path = Path(self.temp.name) / "foods.csv"
        path.write_text(",".join(FOOD_HEADER) + "\nRice,360,7,1,80\n", encoding="utf-8")
        self.assertEqual(len(self.food_importer.preview(path).foods), 1)


class DiaryCsvRepairTests(RepairTestCase):
    def test_clean_table_and_unknown_food_are_not_repair_issues(self):
        self.assertEqual(self.diary_importer.issues_for(table(["food_name", "grams"], ["Oats", "50"])), ())
        # an unknown food is a catalogue question answered in the review screen ("did you mean"), not a typo in a value
        self.assertEqual(self.diary_importer.issues_for(table(["food_name", "grams"], ["Ots", "50"])), ())

    def test_missing_mandatory_column(self):
        issues = self.diary_importer.issues_for(table(["description", "serving"], ["Oats", "50"]))
        self.assertTrue(issues)
        self.assertEqual({issue.row for issue in issues}, {0})
        self.assertIn("Food name", " ".join(issue.message for issue in issues))

    def test_format_error_carries_the_rows(self):
        broken = table(["description", "serving"], ["Oats", "50"])
        with self.assertRaises(DiaryCsvFormatError) as caught:
            self.diary_importer.preview_table(broken)
        self.assertIs(caught.exception.table, broken)
        self.assertIn("Expected header", str(caught.exception))

    def test_bad_amount_meal_and_name_are_pinned_to_their_cells(self):
        issues = self.diary_importer.issues_for(table(
            ["food_name", "grams", "meal"],
            ["Oats", "fifty", "Breakfast"],
            ["Oats", "50", "Brunch"],
            ["", "50", "Lunch"],
            ["Oats", "50", "Lunch"],
        ))
        self.assertEqual({(issue.row, issue.column) for issue in issues}, {(1, 1), (2, 2), (3, 0)})

    def test_fixing_the_cells_in_memory_clears_the_issues(self):
        rows = [["food_name", "grams"], ["Oats", "fifty"]]
        self.assertTrue(self.diary_importer.issues_for(table(*rows)))
        rows[1][1] = "50"
        self.assertEqual(self.diary_importer.issues_for(table(*rows)), ())
        self.assertEqual(self.diary_importer.preview_table(table(*rows)).importable_count, 1)


if __name__ == "__main__":
    unittest.main()
