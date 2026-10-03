import tempfile
import unittest
from decimal import Decimal, InvalidOperation
from pathlib import Path

from calorie_tracker.domain.diary import MealPortion, normalize_portions
from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food
from calorie_tracker.infrastructure.csv_headers import DIARY_FIELD_ALIASES, FOOD_FIELD_ALIASES, analyze_headers
from calorie_tracker.infrastructure.csv_reading import detect_delimiter, parse_decimal, read_csv_rows
from calorie_tracker.infrastructure.database import Database
from calorie_tracker.infrastructure.diary_csv_importer import CsvDiaryImporter, DiaryCsvFormatError
from calorie_tracker.infrastructure.importer import CsvFoodImporter, ImportFormatError
from calorie_tracker.infrastructure.repositories import DiaryRepository, FoodRepository, RecipeRepository
from calorie_tracker.application.diary import DiaryService


class HeaderFlexibilityTests(unittest.TestCase):
    def test_amount_column_accepts_grams_eaten_grams_eaten_with_space_and_grams(self):
        for header in ("grams_eaten", "grams eaten", "Grams", "Grams Eaten", "grams_eaten (all meals)",
                       "Amount (g)", "quantity", "weight (g)"):
            analysis = analyze_headers(["food_name", header], DIARY_FIELD_ALIASES)
            self.assertEqual(analysis.positions.get("amount_g"), 1, header)

    def test_units_parentheses_and_typos_are_understood_but_marked_approximate(self):
        analysis = analyze_headers(
            ["Food", "Calories (kcal)", "Protien", "Fat per 100g", "Carbohydrate", "calories total"],
            FOOD_FIELD_ALIASES,
        )
        self.assertEqual(
            analysis.positions,
            {"food_name": 0, "calories": 1, "protein": 2, "fat": 3, "carbohydrates": 4},
        )
        approximate = {match.field for match in analysis.matches if match.how == "approximate"}
        self.assertEqual(approximate, {"protein"})
        self.assertIn("calories total", analysis.ignored)

    def test_total_columns_are_never_guessed_as_per_100g_fields(self):
        analysis = analyze_headers(["carbohydrates total", "protein total", "fat total"], FOOD_FIELD_ALIASES)
        self.assertEqual(analysis.positions, {})


class ReadingTests(unittest.TestCase):
    def test_numbers_with_decimal_commas_units_and_spaces(self):
        self.assertEqual(parse_decimal("45,5"), Decimal("45.5"))
        self.assertEqual(parse_decimal(" 45 g "), Decimal("45"))
        self.assertEqual(parse_decimal("1 234,5"), Decimal("1234.5"))
        self.assertEqual(parse_decimal("1,234.5"), Decimal("1234.5"))
        self.assertEqual(parse_decimal("120 kcal"), Decimal("120"))
        for bad in ("", "abc", "g"):
            with self.assertRaises(InvalidOperation):
                parse_decimal(bad)

    def test_delimiters_and_cyrillic_windows_encoding_are_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bg.csv"
            path.write_bytes("храна;грамове\nОвес;45,5\n".encode("cp1251"))
            table = read_csv_rows(path)
            self.assertEqual(table.delimiter, ";")
            self.assertEqual(table.rows[1], ["Овес", "45,5"])
        self.assertEqual(detect_delimiter("a\tb\tc\n1\t2\t3\n"), "\t")
        self.assertEqual(detect_delimiter("a,b,c\n1,2,3\n"), ",")


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Database(Path(self.temp_dir.name) / "data" / "tracker.sqlite3")
        self.database.initialize()
        self.foods = FoodRepository(self.database)
        self.recipes = RecipeRepository(self.database, self.foods)
        self.diary_repo = DiaryRepository(self.database)
        self.service = DiaryService(self.foods, self.recipes, self.diary_repo)
        self.foods.save(Food("oats", "Oats", Nutrients(calories=Decimal("380"))))

    def write(self, name: str, text: str) -> Path:
        path = Path(self.temp_dir.name) / name
        path.write_text(text, encoding="utf-8")
        return path


class DiaryImporterFlexibilityTests(_Fixture):
    def test_semicolon_file_with_decimal_commas_units_and_extra_spaces(self):
        path = self.write("d.csv", "Food;Grams eaten;Meal\n  Oats  ;45,5 g;snack\n")
        preview = CsvDiaryImporter(self.foods).preview(path)
        row = preview.rows[0]
        self.assertTrue(row.is_importable)
        self.assertEqual((row.amount_g, row.meal), (Decimal("45.5"), "Snacks"))
        self.assertEqual(preview.delimiter, ";")
        self.assertEqual(preview.header_row, 1)
        self.assertEqual({m.field for m in preview.column_matches}, {"food_name", "amount_g", "meal"})

    def test_unknown_food_gets_a_did_you_mean_hint_and_clear_amount_message(self):
        path = self.write("d.csv", "food_name,grams\nOat,50\nOats,lots\nOats,\n")
        rows = CsvDiaryImporter(self.foods).preview(path).rows
        self.assertIn("Did you mean 'Oats'?", rows[0].error)
        self.assertIn("'lots' is not a number", rows[1].error)
        self.assertIn("empty", rows[2].error)

    def test_missing_amount_column_explains_what_was_found(self):
        path = self.write("d.csv", "food_name,notes\nOats,x\n")
        with self.assertRaises(DiaryCsvFormatError) as error:
            CsvDiaryImporter(self.foods).preview(path)
        message = str(error.exception)
        self.assertIn("Amount (g) MISSING", message)
        self.assertIn("Food name found", message)
        self.assertIn("food_name,grams_eaten,meal", message)


class FoodImporterFlexibilityTests(_Fixture):
    def test_review_rows_and_mapping_describe_the_whole_file(self):
        path = self.write(
            "f.csv",
            "name;kcal;protein;fat;carbs\nBarley;120,5;5;4;20\nBroken;abc;5;4;20\nBarley;1;1;1;1\n",
        )
        preview = CsvFoodImporter(self.foods).preview(path)
        self.assertEqual([r.status for r in preview.rows], ["ready", "needs_correction", "duplicate"])
        self.assertEqual(preview.delimiter, ";")
        self.assertEqual(str(preview.foods[0].food.nutrients_per_100g.calories), "120.5")
        self.assertIn("kcal", preview.rows[1].message.casefold())

    def test_missing_required_columns_report_the_closest_header(self):
        path = self.write("f.csv", "name,kcal\nOats,100\n")
        with self.assertRaises(ImportFormatError) as error:
            CsvFoodImporter(self.foods).preview(path)
        self.assertIn("Closest header", str(error.exception))
        self.assertIn("Protein MISSING", str(error.exception))


class SplitTests(_Fixture):
    def test_portions_merge_drop_zeroes_and_must_add_up(self):
        parts = normalize_portions(Decimal("500"), [("Dinner", Decimal("300")), ("Lunch", Decimal("200")),
                                                    ("Snacks", Decimal("0"))])
        self.assertEqual(parts, (MealPortion("Lunch", Decimal("200")), MealPortion("Dinner", Decimal("300"))))
        with self.assertRaises(ValueError):
            normalize_portions(Decimal("500"), [("Lunch", Decimal("200"))])
        with self.assertRaises(ValueError):
            normalize_portions(Decimal("500"), [("Brunch", Decimal("500"))])
        merged = normalize_portions(Decimal("500"), [("Lunch", Decimal("100")), ("Lunch", Decimal("400"))])
        self.assertEqual(merged, (MealPortion("Lunch", Decimal("500")),))

    def test_rounding_gap_goes_to_largest_portion(self):
        parts = normalize_portions(Decimal("100.004"), [("Lunch", Decimal("40")), ("Dinner", Decimal("60"))])
        self.assertEqual(sum(p.amount_g for p in parts), Decimal("100.004"))

    def test_split_entry_replaces_original_atomically_and_keeps_nutrition(self):
        entry = self.service.add_item("2026-10-01", "Lunch", "oats", Decimal("500"))
        parts = self.service.split_entry(
            entry.id, [MealPortion("Lunch", Decimal("200")), MealPortion("Dinner", Decimal("300"))]
        )
        stored = self.service.entries_for_day("2026-10-01")
        self.assertEqual(stored, parts)
        self.assertEqual(sum(e.nutrients.calories for e in stored), entry.nutrients.calories)
        self.assertIsNone(self.diary_repo.get(entry.id))

    def test_failed_split_leaves_the_entry_untouched(self):
        entry = self.service.add_item("2026-10-01", "Lunch", "oats", Decimal("500"))
        with self.assertRaises(ValueError):
            self.service.split_entry(entry.id, [MealPortion("Lunch", Decimal("200"))])
        self.assertEqual(self.service.entries_for_day("2026-10-01"), (entry,))
        with self.assertRaises(KeyError):
            self.service.split_entry("missing", [MealPortion("Lunch", Decimal("1"))])

    def test_first_logged_date(self):
        self.assertIsNone(self.service.first_logged_date())
        self.service.add_item("2026-10-05", "Lunch", "oats", Decimal("5"))
        self.service.add_item("2026-10-02", "Lunch", "oats", Decimal("5"))
        self.assertEqual(self.service.first_logged_date(), "2026-10-02")


if __name__ == "__main__":
    unittest.main()
