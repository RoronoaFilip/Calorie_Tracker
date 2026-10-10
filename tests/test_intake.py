import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

from calorie_tracker.infrastructure.intake import (
    KIND_DIARY, KIND_FOODS, KIND_IMAGE, KIND_RECIPES, KIND_UNKNOWN_CSV, build_intake_plan, diary_date_from_name,
)

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
FOODS = "food_name,basis,calories,fat,saturated_fat,carbohydrates,sugars,protein,fiber,omega_3,omega_6\nOats,g,380,7,1,60,1,13,10,,\n"
DIARY = "food_name,grams_eaten,meal\nOats,45,Breakfast\n"
RECIPES = "recipe_name,yield_g,ingredient,amount,unit\nPorridge,300,Oats,50,\n"


class DiaryDateTests(unittest.TestCase):
    def test_dates_in_file_names(self):
        self.assertEqual(diary_date_from_name("diary-2026-10-05.csv"), date(2026, 10, 5))
        self.assertEqual(diary_date_from_name("Diary-2026-10-05 (1).csv"), date(2026, 10, 5))
        self.assertIsNone(diary_date_from_name("diary-2026-02-30.csv"))
        self.assertIsNone(diary_date_from_name("meals.csv"))


class BuildIntakePlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / "work"

    def write(self, name, content):
        path = self.root / name
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8-sig"))
        return path

    def test_mixed_batch_is_ordered_foods_photos_recipes_diary_unknown(self):
        paths = [
            self.write("diary-2026-10-06.csv", DIARY + "Milk,200,Lunch\n"),
            self.write("odd.csv", "a,b\n1,2\n"),
            self.write("recipes.csv", RECIPES),
            self.write("barcode.jpg", JPEG),
            self.write("foods.csv", FOODS),
            self.write("diary-2026-10-05.csv", DIARY),
        ]
        plan = build_intake_plan(paths, self.work)
        self.assertEqual(
            [item.kind for item in plan.items],
            [KIND_FOODS, KIND_IMAGE, KIND_RECIPES, KIND_DIARY, KIND_DIARY, KIND_UNKNOWN_CSV],
        )
        self.assertEqual([item.diary_date for item in plan.items if item.kind == KIND_DIARY],
                         [date(2026, 10, 5), date(2026, 10, 6)])
        self.assertEqual(plan.problems, ())

    def test_zip_is_expanded_and_dates_come_from_the_original_name(self):
        archive = self.root / "export.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("foods.csv", FOODS)
            bundle.writestr("diary-2026-10-05.csv", DIARY)
            bundle.writestr("photos/barcode-001.jpg", JPEG)
        plan = build_intake_plan([archive], self.work)
        self.assertEqual([item.kind for item in plan.items], [KIND_FOODS, KIND_IMAGE, KIND_DIARY])
        self.assertEqual(plan.items[2].diary_date, date(2026, 10, 5))
        self.assertIn("export.zip/", plan.items[0].label)

    def test_bad_zip_and_unsupported_files_become_problems_but_the_rest_still_imports(self):
        broken = self.write("broken.zip", b"not a zip")
        notes = self.write("notes.txt", "hello")
        good = self.write("foods.csv", FOODS)
        plan = build_intake_plan([broken, notes, good], self.work)
        self.assertEqual([item.kind for item in plan.items], [KIND_FOODS])
        self.assertEqual(len(plan.problems), 2)
        self.assertTrue(any("notes.txt" in problem for problem in plan.problems))

    def test_identical_files_are_included_once(self):
        first = self.write("a.csv", DIARY)
        second = self.write("b.csv", DIARY)
        plan = build_intake_plan([first, second], self.work)
        self.assertEqual(len(plan.items), 1)
        self.assertEqual(len(plan.problems), 1)

    def test_impossible_or_missing_date_keeps_the_selected_day(self):
        paths = [self.write("diary-2026-02-30.csv", DIARY), self.write("meals.csv", DIARY + "Milk,200,Lunch\n")]
        plan = build_intake_plan(paths, self.work)
        self.assertEqual([item.diary_date for item in plan.items], [None, None])

    def test_a_folder_or_missing_path_is_a_problem(self):
        plan = build_intake_plan([self.root, self.root / "nope.csv"], self.work)
        self.assertEqual(plan.items, ())
        self.assertEqual(len(plan.problems), 2)


if __name__ == "__main__":
    unittest.main()
