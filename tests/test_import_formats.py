import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from calorie_tracker.domain.nutrition import Nutrients
from calorie_tracker.domain.recipes import Food
from calorie_tracker.infrastructure.csv_kind import CsvKind, classify_csv_text
from calorie_tracker.infrastructure.database import Database
from calorie_tracker.infrastructure.diary_csv_importer import CsvDiaryImporter
from calorie_tracker.infrastructure.importer import CsvFoodImporter
from calorie_tracker.infrastructure.recipe_csv_importer import CsvRecipeImporter
from calorie_tracker.infrastructure.repositories import FoodRepository, RecipeRepository
from calorie_tracker.presentation.import_formats import FORMAT_DOCS, HELP_DOCUMENT_STYLE, OTHER_FILES, render_help_html


class DocumentedFormatsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        database = Database(Path(self.temp.name) / "data" / "tracker.sqlite3")
        database.initialize()
        self.foods = FoodRepository(database)
        self.foods.save(Food("oats", "Oats", Nutrients(calories=Decimal("380"))))
        self.importers = {
            CsvKind.FOODS: CsvFoodImporter(self.foods),
            CsvKind.DIARY: CsvDiaryImporter(self.foods),
            CsvKind.RECIPES: CsvRecipeImporter(self.foods, RecipeRepository(database, self.foods)),
        }

    def test_the_three_formats_are_documented(self):
        self.assertEqual([doc.kind for doc in FORMAT_DOCS], [CsvKind.FOODS, CsvKind.DIARY, CsvKind.RECIPES])
        self.assertTrue(OTHER_FILES)

    def test_every_documented_example_is_recognised_and_imports_without_problems(self):
        for doc in FORMAT_DOCS:
            with self.subTest(kind=doc.kind):
                self.assertEqual(classify_csv_text(doc.example_text), doc.kind)
                importer = self.importers[doc.kind]
                table = importer.read_text(doc.example_text)
                self.assertEqual(importer.issues_for(table), ())

    def test_header_lines_use_only_documented_columns(self):
        for doc in FORMAT_DOCS:
            self.assertEqual(len(doc.header), len(doc.example_row.split(",")))
            self.assertTrue(set(doc.required) <= set(doc.header) | {"amount_g"})

    def test_alternative_names_come_from_the_importers_alias_tables(self):
        diary = next(doc for doc in FORMAT_DOCS if doc.kind is CsvKind.DIARY)
        names = dict(diary.also_accepted)
        self.assertIn("amount", names["grams_eaten"])
        self.assertIn("name", names["food_name"])

    def test_the_help_page_sets_its_own_readable_colours(self):
        html = render_help_html()
        self.assertIn("color:#243041", html)  # body text is dark on the light box, whatever the system theme
        self.assertIn("#243041", HELP_DOCUMENT_STYLE)
        self.assertIn("background-color: #dfe8f5", HELP_DOCUMENT_STYLE)  # code samples


if __name__ == "__main__":
    unittest.main()
