import tempfile
import unittest
from pathlib import Path

from calorie_tracker.infrastructure.csv_kind import CsvKind, classify_csv, classify_csv_text

FOODS_HEADER = "food_name,basis,calories,fat,saturated_fat,carbohydrates,sugars,protein,fiber,omega_3,omega_6"
DIARY_HEADER = "food_name,grams_eaten,meal"
RECIPES_HEADER = "recipe_name,yield_g,ingredient,amount,unit"


class ClassifyCsvTextTests(unittest.TestCase):
    def test_the_three_exact_headers(self):
        self.assertEqual(classify_csv_text(FOODS_HEADER + "\nOats,g,380,7,1,60,1,13,10,,\n"), CsvKind.FOODS)
        self.assertEqual(classify_csv_text(DIARY_HEADER + "\nOats,45,Breakfast\n"), CsvKind.DIARY)
        self.assertEqual(classify_csv_text(RECIPES_HEADER + "\nPorridge,300,Oats,50,\n"), CsvKind.RECIPES)

    def test_a_recipe_header_is_not_mistaken_for_a_diary_file(self):
        self.assertEqual(classify_csv_text("name,ingredient,amount\nPorridge,Oats,50\n"), CsvKind.RECIPES)

    def test_dialects_bom_and_leading_blank_lines(self):
        text = "\ufeff\n\n" + "food_name;grams_eaten;meal\nOats;45,5;Breakfast\n"
        self.assertEqual(classify_csv_text(text), CsvKind.DIARY)
        tabbed = "food_name\tcalories\tprotein\tfat\tcarbs\nOats\t380\t13\t7\t60\n"
        self.assertEqual(classify_csv_text(tabbed), CsvKind.FOODS)

    def test_a_title_line_before_the_header_is_skipped(self):
        self.assertEqual(classify_csv_text("My diary\n" + DIARY_HEADER + "\nOats,45,Breakfast\n"), CsvKind.DIARY)

    def test_unknown_when_there_is_no_recognisable_header(self):
        for text in ("a,b,c\n1,2,3\n", "", "Oats,45.5,Breakfast\n", "\n\n"):
            with self.subTest(text=text):
                self.assertEqual(classify_csv_text(text), CsvKind.UNKNOWN)

    def test_foods_and_diary_at_once_is_ambiguous(self):
        text = "food_name,grams,calories,protein,fat,carbs\nOats,50,190,6,3,30\n"
        self.assertEqual(classify_csv_text(text), CsvKind.UNKNOWN)

    def test_unparseable_text_is_unknown_not_an_error(self):
        self.assertEqual(classify_csv_text('food_name,grams_eaten\n"Oats,45\n'), CsvKind.UNKNOWN)


class ClassifyCsvFileTests(unittest.TestCase):
    def test_file_and_text_agree(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "x.csv"
            content = DIARY_HEADER + "\nOats,45,Breakfast\n"
            path.write_text(content, encoding="utf-8-sig")
            self.assertEqual(classify_csv(path), classify_csv_text(content))
            self.assertEqual(classify_csv(Path(folder) / "missing.csv"), CsvKind.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
