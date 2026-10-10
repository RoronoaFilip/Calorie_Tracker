import csv
import io
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food
from calorie_tracker.infrastructure.csv_kind import CsvKind
from calorie_tracker.infrastructure.csv_reading import read_csv_text
from calorie_tracker.infrastructure.database import Database
from calorie_tracker.infrastructure.diary_csv_importer import CsvDiaryImporter
from calorie_tracker.infrastructure.importer import CsvFoodImporter
from calorie_tracker.infrastructure.paste_analysis import PasteState, analyze_paste, locate_cells
from calorie_tracker.infrastructure.recipe_csv_importer import CsvRecipeImporter
from calorie_tracker.infrastructure.repositories import FoodRepository, RecipeRepository

FOODS_HEADER = "food_name,basis,calories,fat,saturated_fat,carbohydrates,sugars,protein,fiber,omega_3,omega_6"


class LocateCellsTests(unittest.TestCase):
    def assert_aligned(self, text):
        table = read_csv_text(text)
        spans = locate_cells(text, table.delimiter)
        self.assertEqual(len(spans), len(table.rows))
        for cells, row in zip(spans, table.rows):
            self.assertEqual(len(cells), len(row))
            for span, value in zip(cells, row):
                parsed = next(csv.reader(io.StringIO(text[span.start:span.end], newline=""), delimiter=table.delimiter), [""])
                self.assertEqual(parsed[0] if parsed else "", value)

    def test_spans_line_up_with_parsed_cells(self):
        cases = [
            "a,b,c\n1,2,3\n",
            'name,note\n"Oats, rolled","said ""hi"""\n',
            'a,b\n"line one\nline two",x\n',
            "a;b;c\r\n1;2;3\r\n\r\n4;5;6",
            "a,b,\n,,\n",
            "x\n\n\ny",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_aligned(text)


class AnalyzePasteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        database = Database(Path(self.temp.name) / "data" / "tracker.sqlite3")
        database.initialize()
        self.foods = FoodRepository(database)
        self.foods.save(Food("oats", "Oats", Nutrients(calories=Decimal("380"))))
        self.foods.save(Food("milk", "Milk", Nutrients(calories=Decimal("60"))))
        self.importers = {
            CsvKind.FOODS: CsvFoodImporter(self.foods),
            CsvKind.DIARY: CsvDiaryImporter(self.foods),
            CsvKind.RECIPES: CsvRecipeImporter(self.foods, RecipeRepository(database, self.foods)),
        }

    def states(self, analysis, text):
        return [(text[h.start:h.end], h.state, h.emphasis) for h in analysis.highlights]

    def test_diary_paste_marks_header_rows_problem_cell_and_unused_column(self):
        text = "My diary\nfood_name,grams_eaten,meal,notes\nOats,45,Breakfast,x\nMilk,abc,Lunch,y\nMilk,200,Lunch,z\n"
        analysis = analyze_paste(text, self.importers)
        self.assertEqual(analysis.kind, CsvKind.DIARY)
        found = self.states(analysis, text)
        self.assertIn(("My diary", PasteState.IGNORED, False), found)
        self.assertIn(("food_name", PasteState.HEADER, False), found)
        self.assertNotIn(("notes", PasteState.HEADER, False), found)
        self.assertIn(("Oats,45,Breakfast,x", PasteState.OK, False), found)
        self.assertIn(("Milk,abc,Lunch,y", PasteState.PROBLEM, False), found)
        self.assertIn(("abc", PasteState.PROBLEM, True), found)
        self.assertEqual(analysis.problem_count, 1)
        self.assertIn("problem", analysis.summary)
        self.assertIn("2 of 3 rows ready", analysis.summary)
        self.assertIn("Not used: notes", analysis.summary)
        self.assertIn("1 line before the header ignored", analysis.summary)

    def test_unknown_food_is_a_warning_with_the_guess_not_a_problem(self):
        text = "food_name,grams_eaten,meal\neggs,50,Breakfast\nOat,30,Lunch\n"
        analysis = analyze_paste(text, self.importers)
        warnings = [h for h in analysis.highlights if h.state is PasteState.WARNING]
        self.assertEqual(len(warnings), 2)
        self.assertEqual(analysis.problem_count, 0)
        self.assertEqual(analysis.warning_count, 2)
        oat = next(h for h in warnings if text[h.start:h.end].startswith("Oat,"))
        self.assertIn("Did you mean 'Oats'", oat.tooltip)
        self.assertIn("suggested as 'Oats' in the review", oat.tooltip)
        self.assertNotIn("suggested as", next(h for h in warnings if text[h.start:h.end].startswith("eggs")).tooltip)

    def test_foods_paste_flags_a_missing_value_in_the_right_cell(self):
        text = FOODS_HEADER + "\nRice,g,130,0.3,0.1,28,0.1,2.7,0.4,,\nBread,g,,3,1,49,5,9,3,,\n"
        analysis = analyze_paste(text, self.importers)
        self.assertEqual(analysis.kind, CsvKind.FOODS)
        self.assertEqual(analysis.problem_count, 1)
        cell = [h for h in analysis.highlights if h.emphasis]
        self.assertEqual(len(cell), 1)
        self.assertEqual(text[cell[0].start:cell[0].end], "")  # the empty calories cell
        self.assertEqual(text[:cell[0].start].splitlines()[-1], "Bread,g,")

    def test_recipes_paste_marks_every_row_of_a_broken_recipe(self):
        text = "recipe_name,yield_g,ingredient,amount,unit\nPorridge,,Oatz,50,\nPorridge,,Milk,200,\n"
        analysis = analyze_paste(text, self.importers)
        self.assertEqual(analysis.kind, CsvKind.RECIPES)
        self.assertEqual(analysis.problem_count, 2)
        rows = [h for h in analysis.highlights if h.state is PasteState.PROBLEM and not h.emphasis]
        self.assertEqual(len(rows), 2)

    def test_text_without_a_header_is_not_recognised(self):
        analysis = analyze_paste("Oats,45.5,Breakfast\n", self.importers)
        self.assertEqual(analysis.kind, CsvKind.UNKNOWN)
        self.assertEqual(analysis.highlights, ())
        self.assertIn("header row", analysis.summary)

    def test_blank_text_says_nothing_and_unparseable_text_reports_the_error(self):
        self.assertEqual(analyze_paste("  \n", self.importers).summary, "")
        broken = analyze_paste('food_name,grams_eaten\n"Oats,45\n', self.importers)
        self.assertIsNotNone(broken.read_error)
        self.assertEqual(broken.highlights, ())

    def test_leading_bom_shifts_nothing(self):
        text = "\ufefffood_name,grams_eaten\nOats,45\n"
        analysis = analyze_paste(text, self.importers)
        header = next(h for h in analysis.highlights if h.state is PasteState.HEADER)
        self.assertEqual(text[header.start:header.end], "food_name")

    def test_large_paste_is_capped(self):
        rows = "".join(f"Oats,{n + 1}\n" for n in range(2000))
        text = "food_name,grams_eaten\n" + rows
        analysis = analyze_paste(text, self.importers, max_rows=100)
        self.assertIn("Showing the first 100 rows", analysis.summary)
        self.assertLessEqual(sum(h.state is PasteState.OK for h in analysis.highlights), 100)


if __name__ == "__main__":
    unittest.main()
